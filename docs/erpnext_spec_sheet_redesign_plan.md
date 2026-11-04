# Spec Sheet and Webflow Publication Redesign: Implementation Plan

**Version:** 0.7
**Date:** 2026-11-04
**Scope:** Staging only. Nothing here is applied to production until the staging test matrix (section 9) passes and the owner approves promotion.

---

## 0. How to use this document (for Claude Code)

This is the only document for this project. Update it as phases change; do not create separate phase notes.

**Status (2026-11-04):** Phases 0 to 4 are done. What was built, the owner changes made along the way, and the staging results are under each phase in section 6 ("As built"). Decisions made during the work are in 4.0 (D49 onward). Open items and cleanup work are in 8.2. Moving to main is section 10. Sections 2 and 3 describe the system as it was at commit `1d8950f`, before this work.

1. Read sections 1 to 5 fully before touching code. Section 6 is the work, in order. Section 8 lists open questions. The appendices explain how the existing system behaves.
2. Do not guess on open questions. Implement what is unblocked, and stop at the first task that depends on an open question. Report what you stopped on.
3. Environment rules:
   - **Repo:** `github.com/kevinschern-illumenate/erpillumenatelighting`, branch **`staging`**, pinned to commit `1d8950f6e1a0b0c44f3c630082f5d7bfe694e54a`. Branch feature work off it and merge back to `staging` only. Do not touch `main`. Deploy to the **staging site only** (`stagingillumenate.v.frappe.cloud`).
   - **n8n:** change only the staging workflow `[STAGING] Spec Gen & Webflow Sync` (ID `NW0NxiyqKyeVrkOJ`). Its webhooks are `https://illumenatelighting.app.n8n.cloud/webhook/staging-generate-spec-sheet` (spec) and `.../webhook/staging-product-sync-v2` (sync). Both use Header Auth with the credential **"STAGING Sync Secret"** (header name `STAGING-Sync-Secret`). Do not edit or publish production workflow `dvCvIpVLwzjgwccF`.
   - **Webflow has no staging site.** Staging writes to the real Webflow site. Follow section 4.11 without exception: staging may only create or modify items that are marked `[staging]`, and those are always hidden from the public. **Superseded for ilLumenate (2026-11-04, D82):** staging now has its own Webflow site, `https://staging-illumenate.webflow.io`. 206 Lighting has no staging site yet and keeps the `[staging]` rules. See 4.11 and 10.8.
   - Work started from `staging` at `d0f760f` (the pinned commit `1d8950f` plus one merge that pointed `trigger_sync_v2` at the `staging-product-sync-v2` URL; Z1 removed that hardcoded URL). The pin is historical now: later phases built on the current `staging` head.
   - **No secrets** in code, commits, logs, or documents. Config key names are given here. Values live in site config and n8n credentials.
   - Locate code by file and function name. Line numbers in this document are from commit `1d8950f`.
4. Facts in sections 2 and 3 are **verified** (from code at `1d8950f` or from the live n8n workflows). Items marked **(verify)** are inferences. Items marked **(proposed)** are design choices not yet confirmed by the owner.
5. After each phase: run its "Done when" checks, record evidence (curl output, execution IDs, screenshots) in that phase's "As built" subsection in section 6, commit, and report.

---

## 1. Goal

Spec sheets are generated from **templates** alone, with no Webflow product record required. A template is tied to a Webflow product only when it is Active. The template's `product_status` is the source of truth for lifecycle. The linked `ilL-Webflow-Product` controls everything Webflow shows. Webflow is touched as little as possible.

**Naming used in this plan.**

- `template_id` is the template record name (`template.name`, from the `template_code` field, for example `KIT-RA01`).
- `template_name` is the human-readable display field (for example `Rainier [SF]-6.5ft Extrusion Kit`).
- The existing n8n code uses `template_name` for the record id. The new APIs use `template_id` to avoid the clash.

---

## 2. Current state (verified)

### 2.1 Systems

| System | Role |
|---|---|
| ERPNext app `illumenate_lighting` on Frappe Cloud (v16) | Source of truth. Production `app.illumenate.lighting`, staging `stagingillumenate.v.frappe.cloud`. |
| Six template doctypes | `ilL-Extrusion-Kit-Template`, `ilL-Tape-Neon-Template`, `ilL-LED-Sheet-Template`, `ilL-Fixture-Template`, `ilL-Driver-Template`, `ilL-Controller-Template`. All use `autoname = field:template_code`. |
| `ilL-Webflow-Product` | Webflow-facing record. Holds the per-type template link fields (`kit_template`, `fixture_template`, `tape_neon_template`, `driver_template`, `controller_template`, `led_sheet_template`). |
| n8n Cloud (`illumenatelighting.app.n8n.cloud`) | Orchestration. Production workflow `dvCvIpVLwzjgwccF` ("Spec Gen & Webflow Sync"). Staging copy `NW0NxiyqKyeVrkOJ`. |
| PDF generator | `github.com/reigine-illuminate/erpnext-pdf-generator`, deployed at `erpnext-pdf-generator.vercel.app/api`. Puppeteer. It receives a payload key named `configurator_options`. Unchanged by this plan. |
| Webflow | Layout pages per product type (the staging workflow fetches them from `illumenate-staging.webflow.io` and `206-lighting.webflow.io`), plus the CMS product collections per brand. Two brands: ilLumenate (`illumenate`) and 206 Lighting (`lighting_206`). |

### 2.2 Spec generation today (workflow W1)

1. The desk button on `ilL-Webflow-Product` calls the ERPNext method `request_spec_sheet` (`api/webflow_export_v2.py`). It checks permission, then posts `{product, product_slug, brand}` to the n8n webhook with the shared-secret header. The secret comes from site config key `n8n_sync_secret`. **The webhook URL is hardcoded to the production path** (see 2.8).
2. n8n `Get Product Info` calls `webflow_export_v2.get_webflow_products` (keyed on the product slug) and receives `message.products[0]`.
3. `Switch` by brand, then `Fetch Webflow Template` (HTML of the layout page for the product type), then `Format Data to Inject` (injects `window.ERP_DATA` plus a mapping script), then the Vercel HTTP request, then `Convert base64 string`.
4. The file name is built in the `Convert base64 string` node from the brand display name and product name (`<Brand>_<Product Name>_Spec Sheet.pdf`), with unsafe characters stripped by a regex that differs between the ilL and 206 versions (the 206 version also strips brackets and dots). No unique suffix is added.
5. `Upload Spec to File Manager` posts multipart to `webflow_export_v2.upload_spec_pdf` (`is_private=0`, folder `Home`).
6. `Update Template Spec Sheet` does a PUT on `/api/resource/<template doctype>/<template record name>` setting `spec_sheet` to the uploaded `file_url`.
7. `Update Webflow?` (IF `custom_webflow_status != Draft`): true goes to `Handoff to Workflow 2`, which POSTs `trigger_sync_v2` as the n8n API user. Then `Job Created?` leads to a success or error response.

### 2.3 ERPNext sync trigger today (`trigger_sync_v2`)

- Permission check (`_require_product_access`: System User plus write on the product). Then `doc.save(ignore_permissions=True)`.
- That save fires the product's `before_save`, which runs `sync_custom_template_data` and mirrors the template's files into the product (2.5). **The spec-sheet mirror runs only because this function re-saves the product.**
- For each enabled row in the product's `target_brands`: `inspect()`. If not ready, `msgprint` and skip. Otherwise `request(docname, brand, "STAGE", hash)`, then `claim(brand, limit=5)`, then `frappe.enqueue(enqueue_n8n_webhook, ...)` posting each claimed job to the hardcoded n8n `product-sync-v2` URL.
- It always requests **STAGE**. `trigger_publish_v2` requests PUBLISH.

### 2.4 Webflow sync today (workflow W2)

- `Set Brand Config` (Code node) reads the collection ID from the job payload. Per the owner, the hardcoded Webflow tokens have been removed. In the staging copy the node now sets `webflow_api_token: null`.
- `Split by Brand`, then a Transform node per brand, then `Exists in Webflow?` (on `remote_item_id`), then create or update, then `Should Publish?` (publish only if `isDraft` and `isArchived` are both false), then `Publish Webflow Item`, then `mark_webflow_synced` (the callback), then respond.
- **Visibility comes from a `switch` on `custom_webflow_status` inside each Transform node:**

| Value | isDraft | isArchived | hidden-from-public |
|---|---|---|---|
| Draft | true | false | true |
| Webflow Draft | false | false | true |
| Publish and Discontinued (one shared case) | false | false | false |
| Archived | false | true | true |
| **`default:` (any other value, including empty)** | false | false | **false (public)** |

- **Correction to earlier drafts:** Discontinued is an explicit case grouped with Publish. It is **not** handled by the default branch. The real risk is the `default:` catch-all. Any value the node does not recognize, a typo or a missing key, publishes the item to the public. If `custom_webflow_status` is renamed and the n8n code still reads the old key, every item hits `default:` and goes public. See Phase 0 task Z3 and section 4.9.
- There is **no unpublish step** in W2.
- Webflow's badge field `product-badge` is fed from `product.product_badge` (the standard field), not from `custom_web_badge`. W2 also sends `documents-json` and `specifications-json`.

### 2.5 Template and product data

Verified in `ill_webflow_product.py`, `web_listing.py`, `web_listing_schema.py`, `hooks.py`, `template_documents.js`, and the six template doctype JSON files.

- Template `product_status` options: `Draft, Active, Internal Only, Discontinued, Archived`. `ACTIVE_STATUSES = (Active, Internal Only)`. `DEFAULT_STATUS` for a new template is `Internal Only`. `apply_product_status` (in each template's `validate`) keeps `product_status` and `is_active` in step: Active and Internal Only give `is_active = 1`, the other three give `0`. Nothing derives the product's Webflow status from it.
- Template `webflow_product` is a **read-only** Link, written by the product's `on_update` (`_update_template_backlink`). The product stores the real link in its per-type link fields.
- Template `spec_sheet` is an Attach field. Templates also have `spec_submittal_template` (Attach). `template_name` is required on the kit, tape/neon and fixture templates and optional on the LED sheet, driver and controller templates.
- `web_listing_schema.py` defines field groups injected into the template doctypes (`_SPEC_SHEET_DATA`, `_LENGTHS`, `_WEIGHT`, `_KIT_COMPONENTS`, `_PHOTOMETRICS`, `_COLORIMETRY`). It already creates a **"Product Data" tab** (a Tab Break labelled `Product Data`). This is the mechanism and location for new template fields.
- Product `before_save` calls `sync_custom_template_data` (`ill_webflow_product.py`, line 3335 to the end of the file, about 1,200 lines). It does three things (see Appendix D):
  1. Part 1: mirrors core fields, writes a `Spec Sheet` row into the product's `documents` table (child `ilL-Child-Webflow-Document`) from the template's `spec_sheet` (title `<product_name> Spec Sheet`), and handles `Spec Submittal` rows, template `custom_documents` rows, and certifications.
  2. Part 2: mirrors the template's configurator options into the product's `configurator_options` table.
  3. Part 3: rebuilds the product's calculated spec rows into `custom_spec_custom`.
  It returns immediately if the product lacks the **site Custom Field** `custom_spec_custom`.
- `PRODUCT_TYPE_TEMPLATE_MAP` maps product type to template link and doctype. `LED Tape`, `COB Tape` and `LED Neon` all share `tape_neon_template`. `Component` and `Accessory` have no template mapping.
- **The product has overlapping fields.** Standard fields exist alongside site Custom Fields that appear to replace them (see Appendix E):

| Standard field on the product | Custom field that overlaps it |
|---|---|
| `product_category` (Link to `ilL-Webflow-Category`; the form relabels it "old-Product Category") | `custom_web_product_category` ("Mirrored from template") |
| `series` (Link to `ilL-Attribute-Series`) | `custom_web_series` |
| `product_badge` (Select: blank, New, On Sale, Quick Ship, Hide) | `custom_web_badge` |
| `dimensions_image` (Attach Image) | `custom_dimensions_image_2` |
| `specifications` (Table, child `ilL-Child-Webflow-Specification`, legacy) | `custom_spec_custom` (Table, child `ilL-Child-Webflow-Spec-Custom`) |
| `documents` (Table) | `custom_documents` (on templates) |

- **None of the 15 `custom_` names referenced in code or n8n is declared in the app.** They exist only as site Custom Fields in the database. Others exist the same way (for example `custom_web_badge` and `custom_min_operating_temp_c_copy` appear on saved records but are not referenced in the repo code).

### 2.6 Publication pipeline (`api/publication.py`, doctypes `ilL-Product-Publication`, `ilL-Publish-Job`)

Simplified in Appendix A. What can make it fail is in Appendix C.

- One **Product Publication** per product and brand holds `state` (`NEEDS_REVIEW, READY, QUEUED, STAGED, LIVE, FAILED, RETIRED`) and four fingerprints: `current_hash`, `approved_hash`, `staged_hash`, `live_hash`. It also holds `approved_by/on`, `staged_on`, `published_on`, `remote_item_id`.
- `payload["active"]` is computed in `_refresh` as: the product's `is_active` **and** the brand's `is_active` **and** the product targets that brand.
- `request(product, brand, operation, hash)` creates an **ilL-Publish-Job** (`STAGE | PUBLISH | RETIRE`) for that exact hash and records the approver. Guards: STAGE and PUBLISH need `payload["active"]` and readiness. PUBLISH also needs the same hash staged and approved, and a `remote_item_id`. RETIRE needs `payload["active"]` false and brand sync enabled. Duplicate requests reuse the job (`request_key`).
- `claim(brand, limit)`: oldest first, marks stale jobs `SUPERSEDED`, skips non-RETIRE jobs when not ready, leases a job for 5 minutes.
- `acknowledge(...)` (from the `mark_webflow_synced` callback): STAGE sets `staged_hash` and `staged_on`. PUBLISH sets `live_hash` and `published_on`. **RETIRE clears `live_hash` and `staged_hash` but not `published_on`.**
- Capabilities (`portal/staff.py`): `catalog` = role **`ilL Catalog Publisher`**, `integration` = role **`ilL Integration`**. System Manager also passes both. `request()` needs `catalog`. `claim`, `acknowledge` and reconcile need `integration`.
- `ilL-Publish-Job` already stores operation, state, hashes, requester, attempts, `last_error`, `completed_on`. This is an existing history.

### 2.7 Live n8n state (2026-10-31)

**Production `dvCvIpVLwzjgwccF`:** the saved draft differs from the active version, so there are **unpublished edits** (the delete chain is disconnected but the nodes remain, `Convert base64 string` feeds `Upload Spec to File Manager` directly, and `Update Webflow?` false goes to the success response only). The owner is keeping the leftover nodes in production for now. **Do not publish these edits until Phase 4 (the redirect) exists.** The editor shows a warning icon on `Upload Spec to File Manager`; the owner says to ignore it for now. Production was not re-checked in the latest pass.

**Staging `NW0NxiyqKyeVrkOJ`** (active, draft equals active, 55 nodes), observed:

- Webhooks and credential as listed in section 0.
- ERPNext base URL `stagingillumenate.v.frappe.cloud` throughout. Layout pages come from `*.webflow.io` domains.
- The old delete chain is **still wired** (`Convert base64 string` to `Find Old Specs in ERP` to `Check for Existing Files` to `Split File Array into Individual Items` to `Delete Old Files` to `Re-attach Binary File Stream` to `Upload Spec to File Manager`).
- `Update Webflow?` false still goes to **both** `Respond to Webhook: Success (W1)` and `Respond to Webhook: Error (W1)` (the misleading "readiness" error for ERP-only products).
- **The Webflow nodes have wrong credentials** (the owner expected them to be set):

| Node | Credential now | Problem |
|---|---|---|
| `(ilL) Webflow: Create Product` | Header Auth "ERP Sync Secret" | Sends the ERP shared secret header to `api.webflow.com`. No Webflow token. |
| `(ilL) Webflow: Update Product` | Header Auth "ERP Sync Secret" | Same. |
| `(206) Webflow: Update Product` | Header Auth "ERP Sync Secret" | Same. |
| `(206) Webflow: Create Product` | Header Auth "ERP Sync Secret" | Same, plus an `Authorization: Bearer null` header (token is now null). |
| `Publish Webflow Item (Update)` | none | Only `Bearer null`. Will fail. |
| `Publish Webflow Item (New)` | Webflow account "Webflow 206 Prod" | Production 206 credential on the shared node, plus `Bearer null`. |

  The Webflow credentials that exist per the owner are named like "Webflow iLLumenate Prod" and "Webflow 206 Prod". Because Webflow has no staging site, staging legitimately uses these. If any W2 run has reached the four Header Auth nodes, the production "ERP Sync Secret" value was sent to Webflow in a request header, so rotate it.

### 2.8 Known problems (to fix as part of this work)

1. **ERPNext hardcodes the production n8n URLs** (`webflow_export_v2.py` lines 2501, 2503, 2567, 2569 for `product-sync-v2` and line 2650 for `generate-spec-sheet-v2`). A staging deploy of commit `1d8950f` calls **production** n8n. Fix before any staging test (task Z1).
2. Staging n8n Webflow credentials are wrong (2.7). Fix (task Z2).
3. The `default:` branch in both Transform nodes makes unknown statuses public (2.4). Fix (task Z3).
4. The staging site is a copy of production data (a product shows "Synced to Webflow" with a recent date), so it likely carries **real Webflow item IDs**. A staging sync could PATCH live items. Fix (4.11, task Z4).
5. `spec_sheet(product)` (guest-callable redirect in `webflow_export_v2.py`) reads `spec_sheet_url` on the product, a field not in the app's doctype definition. It cannot work as written. Replace it (Phase 4).
6. `sync_custom_template_data` silently does nothing on any site lacking `custom_spec_custom`. Staging and production may differ.
7. The product's `documents` Select options do not include `Spec Submittal`, but the mirror code writes that type **(verify)**.
8. W2 derives visibility from `custom_webflow_status` while the pipeline tracks STAGE and PUBLISH separately. They can disagree: a "Publish" product goes public during a STAGE job, and `published_on` is set only by PUBLISH jobs **(verify)**.
9. `enqueue_n8n_webhook` must send the shared-secret header now that W2 requires it **(verify)**.
10. The readiness check **blocks Internal Only templates entirely** and the pipeline blocks STAGE and PUBLISH for inactive products. Both conflict with decision D4 (sunset). See 4.4 and Appendix C.
11. Mixed ERPNext base URLs in the production workflow. Decision: production uses `app.illumenate.lighting` everywhere (D38).

---

## 3. Verified facts that constrain the design

- The product mirror runs on **product save**. Any design where the template owns the data must call the same mirror logic from the template side.
- `request()` blocks STAGE and PUBLISH for inactive payloads, and `evaluate()` fails readiness for Internal Only templates. A page that must stay public as "Discontinued" (a Discontinued template, or Internal Only after being public) conflicts with both (4.4).
- `published_on` survives RETIRE. It is the best durable "published before" signal, but only PUBLISH jobs set it today.
- Files under `/files/` are normally served directly from disk by the web server. The stable URL is therefore a separate route, not a file (4.7).
- The staging Webflow target is the real site (4.11).
- The n8n nodes read legacy payload key names (for example `custom_webflow_status`, `custom_dimensions_image_2`, `custom_compatible_power_supplies`, `custom_webflow_description`, `configurator_options`). Renames break them unless an adapter keeps the old keys (4.6, 4.9).

---

## 4. Target design

### 4.0 Decision log (owner decisions)

| ID | Decision |
|---|---|
| D1 | Template status is the source of truth. The product's stage sits underneath it (layered model, 4.3). |
| D2 | Link ownership is flipped: the template holds the real link, the product is the backlink (4.2). |
| D3 | `webflow_product` is required when the template is Active. Changing status to Active with no link opens a popup (Create new, Link existing, Cancel), handled in one server call. **Changed by D60 (2026-10-31):** the Webflow Product is required for the new status **Active + Live**, not for plain Active. |
| D4 | Internal Only on a published product behaves as Discontinued: the page stays up until the template is Archived. |
| D5 | Re-activation: when a template returns to Active from Discontinued or Archived, the product stage returns to Webflow Draft and a human click is required to go public again. (Agreed in review.) |
| D6 | Stable URL: `/spec-sheets/<template.name>.pdf`, for example `/spec-sheets/kit-ra01.pdf`. The record name never changes. No display-name alias. **Changed by D75 (2026-11-03):** the link carries the brand, `/spec-sheets/<brand>_<record name, lowercase>.pdf`. A link without the brand still resolves. |
| D7 | File name on disk for now: `<template_name>_Spec Sheet.pdf`, for example `Rainier [SF]-6.5ft Extrusion Kit_Spec Sheet.pdf`. No brand prefix. **Superseded by D75 (2026-11-03):** `<Brand>_<Display Name>_Spec Sheet.pdf`. |
| D8 | Automatic pushes: yes, debounced by a few minutes, and only when readiness passes. |
| D9 | The template button is dynamic: "Generate Spec" when no sync applies, "Generate Spec & Sync to Webflow" otherwise. |
| D10 | The template owns spec data. The product owns Webflow presentation. Target Brands lives on the template and mirrors to the product. |
| D11 | n8n: remove the file-name cleanup from the Convert base64 nodes. Delete the orphaned delete-chain nodes in the **staging** workflow only. Production keeps them for now. |
| D12 | Publication History is a read-only view of existing `ilL-Publish-Job` records. No new table. |
| D13 | W2 gets an unpublish step in n8n. |
| D14 | Active, stage Webflow Draft, published before: hide the item (hidden-from-public ON). The hide is applied automatically. (Confirmed.) |
| D15 | Superseded by D33: the product stage "Draft" no longer exists. |
| D16 | Archived and published before (stage or template): do not unpublish or archive automatically. Return the item to Webflow Draft (hidden), flag it for human review, and notify the owner. |
| D17 | One brand per template. |
| D18 | ERPNext orchestrates spec then sync. n8n W1 is spec-only. (Accepted DC1.) **As built (D69):** n8n still uploads the PDF and sets the template's `spec_sheet`; ERPNext's `register_spec_sheet` checks it afterwards. |
| D19 | `spec_sheet` keeps the real file. New `spec_sheet_public_url` holds the stable URL. (Accepted DC2.) |
| D20 | One `resolve_webflow_state` function drives the button label, the pipeline operation and the n8n payload. (Accepted DC3.) |
| D21 | Template `on_update` pushes mirrors to the linked product. The product's `before_save` calls the same function as a fallback. Guard against recursion. (Accepted DC4.) |
| D22 | `target_brands` stays a table on the template, validated to one enabled row. (Accepted DC5.) |
| D23 | Work against branch `staging` at commit `1d8950f`. Deploy to the staging site only. |
| D24 | Retention of old spec files: keep the newest 2. **Superseded by D76 (2026-11-03):** older files are unattached, not deleted. |
| D25 | Part Number Builder: the table fieldname becomes `part_number_builder`, child doctype `ilL-Child-Webflow-Configurator-Option`, column names unchanged. Applies to the template and the product mirror. **Superseded by D58 and D59:** the configurator table is `part_no_configurator` on all six templates (and, later, on the product). |
| D26 | Component and Accessory products keep their own editable Target Brands until they get templates. |
| D27 | Changing a template's brand is blocked once its product has been published on the old brand. Before that it is allowed freely. |
| D28 | Permission for generate, sync and related actions: System User, plus write on the template, plus role `ilL Catalog Publisher` (the existing `catalog` capability; System Manager also passes). |
| D29 | Internal Only back to Active resumes the previous stage. |
| D30 | Archive review has a **Confirm archive** action. Notify `reigine@illumenate.lighting` and `kevins@illumenate.lighting`. **While testing on staging (D83):** notifications go to the owner only; Kevin is added back on main. |
| D31 | Webflow testing from staging writes to the real site. Items are `[staging]` versions. They may be published but are always hidden-from-public (4.11). **Changed by D82 (2026-11-04):** ilLumenate staging now writes to its own staging Webflow site. The rule still applies to 206 Lighting. |
| D32 | Resolution order is template status, then published before, then the product's stage. |
| D33 | The product stage "Draft" is removed. A linked, Active template jumps straight to Webflow Draft, so the draft is viewable in Webflow without a click. ERP-only is represented by not being linked, or by the template not being Active. |
| D34 | `custom_web_product_category` replaces `product_category`. The template owns it and the product mirrors it. Final fieldname: `web_product_category` (Q18d, approved). **Superseded by D51 and D80:** the product's standard `product_category` mirrors the template; `web_product_category` was removed. |
| D35 | Every `custom_` field on the app's own doctypes becomes a standard field, renamed without the prefix. On any name conflict, stop and ask the owner. **Names changed by D56:** product fields take the prefix `webflow_`, template fields no prefix. Done in Phase 1b. |
| D36 | `custom_webflow_status` becomes `webflow_status`. `custom_web_badge` becomes `web_badge`, stays a **purely manual** field, and gains **no** `Discontinued` option. `web_badge` replaces the standard `product_badge` entirely (Q18f). A new read-only checkbox `is_discontinued` is checked whenever the page is Discontinued, whether through the stage or through the template (D48), and unchecked otherwise. The Webflow-side logic that lets `is_discontinued` override `web_badge` is added later (R1, Phase 9). **Changed by D50 and D56:** the field is `webflow_badge`, options blank, New, On Sale, Quick Ship (no Hide). |
| D37 | The data returned to the spec flow ("Get Product Info") is restructured so it is clear which information comes from the template and which from the product (4.6). |
| D38 | n8n uses `app.illumenate.lighting` for production ERPNext calls. The staging workflow uses the staging host. |
| D39 | The rewrite of the n8n `Format Data to Inject` and `Transform to Webflow Format` nodes is **deferred** until the ERP templates and products are in a good place (Phase 9). An adapter keeps the existing nodes working meanwhile. |
| D40 | A blocking progress dialog (fully opaque) appears for **Generate Spec, Generate Spec & Sync to Webflow, and Sync to Webflow** (4.13). |
| D41 | Template fields in 4.1 go on the template's **Product Data** tab. |
| D42 | Staging uses the webhooks and credential listed in section 0. |
| D43 | Specification rows (Q7): keep today's rule on templates (rows with the managed labels are rebuilt on every save, rows with other labels are kept). Omit placeholder rows (literal "TBD"). Treat a 0 and 0 temperature range as "not set" and omit it. |
| D44 | Lifecycle status changes (template status or product stage) are not debounced. Field edits are debounced (default 5 minutes). Retirement is not readiness-gated in `claim()` and goes out promptly (Q13). |
| D45 | A template set back to Draft after its product was public: hide the item, flag it for review and notify, the same as Archived (Q17). |
| D46 | `custom_dimensions_image_2` is deleted outright, not renamed. The template gets `dimensions_image`. The product keeps its standard `dimensions_image` field as is (Q18c). |
| D47 | Rename conflicts approved as recommended (Q18a, b, d, e): `custom_documents` becomes `other_documents`; the new spec table is `specifications` and the legacy table becomes `specifications_legacy`; `web_product_category` replaces `product_category`; `web_series` replaces `series`. **Partly superseded:** category and series by D51 and D80; on the product the spec table is `webflow_specifications` and the legacy table keeps `specifications` (D56). `other_documents` and the template's `specifications` stand. |
| D48 | `is_discontinued` is computed from the resolver's effective state, not only from `webflow_status` (Q19). Checked for a Discontinued stage, a Discontinued template with a published product, and an Internal Only template with a published product. Refreshed when the template's status changes. **Extended by D63 (2026-11-02):** also checked when the stage is Archived and the product has been published. |
| D49 | `webflow_status` keeps the option **"Published"** (the stored value). Wherever this plan says stage "Publish", read "Published". (Owner, 2026-10-31, Phase 0 S5.) |
| D50 | `web_badge` (now `webflow_badge`, D56) options: blank, New, On Sale, Quick Ship. **No "Hide"** (and no "None"). Migration: "None" becomes blank. A `product_badge` value of "Hide" becomes blank too, and the migration report lists those products. (Owner, 2026-10-31.) |
| D51 | Category and series on the product simply mirror the template's existing `product_category` and `series` fields. No new `web_product_category` or `web_series` fields on the template. On the product, the existing standard `product_category` and `series` Links (which the export and the publication pipeline already read) become read-only mirrors for templated products, and the duplicates `custom_web_product_category` and `custom_web_series` are **deleted, not renamed**. Supersedes the category and series parts of D34 and D47. (Owner, 2026-10-31. As built, Phase 1b first kept them as read-only copies `web_product_category` and `web_series`; Phase 4 removed both, D80.) |
| D52 | Certification badge fields: `badge_image_dark`, `badge_image_206_dark`, `badge_image_206_light`. **Superseded by D74 (2026-11-03):** `badge_image_dark`, `badge_image_light_206`, `badge_image_dark_206`. |
| D53 | Delete `custom_min_operating_temp_c_copy` and `custom_column_break_lgzvl`. (Done in Phase 1b.) |
| D54 | The Tape/Neon template gets a real category Link `webflow_category` (Link to `ilL-Webflow-Category`), so its products' `product_category` mirrors from the template like the other five. The existing Select `product_category` on that template stays: it is the tape family that readiness and the configurators use. |
| D55 | Products whose current `product_category` or `series` differs from the template's are listed by the migration and it stops for owner review before anything is changed. |
| D56 | Naming for the `custom_` conversion (supersedes the names in D35, D36 and D47 where they differ): fields on `ilL-Webflow-Product` take the prefix **`webflow_`**; fields on the six templates take **no prefix**. Mapping in Phase 0 "As built" (S5). New fields the plan adds (not conversions) keep the plan's names, for example `is_discontinued` on the product and `specifications`, `sublabel`, `dimensions_image` on the templates. |
| D57 | Certifications are owned by the template. All six templates have a `certifications` table on the Product Data tab (the four existing tables move there with the same fieldname and child doctype; Kit and Fixture get it through `web_listing_schema.py`). The product's `certifications` table becomes a read-only mirror. Component and Accessory products keep an editable table. All the logic that fills the product's rows is kept (per-brand badge JSON, now `webflow_badge_images`, attribute links, export payload, spec row). Only the source of the list changes. (Owner, 2026-10-31.) |
| D58 | The Fixture template keeps its existing `part_number_builder` (part-number sections, child `ilL-Child-PN-Builder-Row`, read by the spec sheet export and the Dry/Wet code sync). The configurator table on **all six templates** is `part_no_configurator` (child `ilL-Child-Webflow-Configurator-Option`, `web_listing_schema.CONFIGURATOR_FIELD`). Only the Fixture template has the older `part_number_builder` sections table. (Owner, 2026-10-31.) |
| D59 | The product's configurator table `configurator_options` is renamed to `part_no_configurator` in Phase 1b, after the Phase 2 adapter that keeps n8n reading the old key (supersedes the product name in D25). **Overtaken by D65:** the product table stays for now and is removed later. |
| D60 | New Product Status **Active + Live**. Options: Draft, Active, Active + Live, Internal Only, Discontinued, Archived. **Active**: offered to dealers and staff in ERPNext and the portal, not listed on the website, no Webflow Product needed. **Active + Live**: offered the same way and listed on the website through its Webflow Product, which is required (setting the status without one is refused, and a Live template cannot be unlinked). Active + Live counts as active everywhere Active did. In the 4.3 table, the "Active" rows 4 to 11 mean **Active + Live**; a plain Active template has no Webflow action of its own. Replaces "required when Active" from D3. (Owner, 2026-10-31.) |
| D61 | When an Active + Live template whose product has been published moves back to plain Active, the page is **hidden** and the owner is **notified**; the owner then decides whether to change the product's Webflow Status. Phase 5: same hide-and-notify path as D45. (Owner, answers Q21.) |
| D62 | A separate final **cleanup phase**, after a spec sheet can be generated and Webflow updated end to end and that has been verified on staging: go over the templates and the Webflow Product, find the fields that were never used, and clean up layout and fields. Until then, layout changes are kept to what the work needs. (Owner, 2026-11-02. Items in 8.2.) |
| D63 | `is_discontinued` is also on when the Webflow Status is Archived and the product has been published. It stays off when the template is Archived. (Owner, 2026-11-02. Extends D48 and changes the expected value for 4.3 row 11.) |
| D64 | All six templates have `display_name`. The Webflow Product's `product_name` copies it on every product save, falling back to `template_name` when it is empty. (Owner, 2026-11-02.) |
| D65 | The product's Configurator Options table, its Auto-Populate check and the product-side calculation **stay for now**, so nothing breaks. They are removed later, after the remaining templates calculate their own steps. (Owner, 2026-11-02.) |
| D66 | Hand-set configurators: the 55 products with steps set up by hand keep what the website shows today. Their templates take those steps and stop calculating (Calculate Configurator on Save off). The 10 fixtures with no steps take the calculated ones. The goal is still that every template calculates; each is switched back once its template options match what is sold. (Owner, 2026-11-02.) |
| D67 | Configurator step order comes from row order. The Step column is hidden and read-only. Step numbers already in use are kept, because the website and n8n match steps by number. (Owner, 2026-11-02.) |
| D68 | Field ownership review (Phase 2b table): `webflow_badge` stays with the product; category, series and Target Brands are owned by the template and mirrored; attribute links and compatible power supplies are owned by the product and calculated from the template; `documents`, the spec links, `is_configurable` and `portal_item` are left as they are and revisited in the cleanup phase (D62). (Owner, 2026-11-02.) |
| D69 | n8n keeps uploading through `upload_spec_pdf` and then setting the template's `spec_sheet` (that is what fills the File's attached-to fields). ERPNext's `register_spec_sheet` then checks the field and sets it if n8n did not. (Owner, Phase 3.) |
| D70 | The spec workflow reads the template, not `legacy`, using the owner's mapping (Phase 3 "As built"). Photometrics, colorimetry and compatible power supplies still come from `legacy`. The template's specifications are complete: they include the rows enriched from the linked spec records. (Owner, 2026-11-02.) |
| D71 | A spec sheet is only made for the template's own Target Brand. A template with no Target Brand, or a request for another brand, is refused. (Owner, 2026-11-02.) |
| D72 | Kit component `webflow_description` is renamed `component_description` (label Description) on the shared child table. Kit templates no longer store the Certifications & Ratings row; the Webflow export still adds it for kit products. (Owner, 2026-11-03.) |
| D73 | Kit Components Description is set on template save from the item's variant attributes: Profile Finish, Lens Lens Color, Endcap Set Endcap Color. Other types, and items without that attribute, keep the typed Description. (Owner, 2026-11-03.) |
| D74 | Certification badge fields ship with the app on `ilL-Attribute-Certification`: `badge_image_dark`, `badge_image_light_206`, `badge_image_dark_206`. These and `badge_image` are Attach fields, so SVG uploads are accepted. Supersedes D52. (Owner, 2026-11-03.) |
| D75 | Spec link and file name carry the brand. Link: `/spec-sheets/<brand>_<record name, lowercase>.pdf`. The brand part must be the template's own Target Brand, else 404; a link without it still resolves. File: `<Brand>_<Display Name>_Spec Sheet.pdf` (Display Name, else Template Name, else record name). Supersedes D6 (format) and D7. (Owner, 2026-11-03.) |
| D76 | Older spec files are unattached, not deleted. After a successful run only the current spec sheet stays attached; older ones stay in File Manager. Supersedes D24. (Owner, 2026-11-03.) |
| D77 | Bulk regeneration goes one template type at a time. Only the Extrusion Kit spec sheet page exists in Webflow so far, so kits go first. Other types keep their current spec sheets and links until their Webflow page is built and that type is regenerated and checked. The owner runs the kit bulk run later, once the foundations are set. (Owner, 2026-11-03 and 2026-11-04.) |
| D78 | Generate Spec checks the template first and lists everything missing; nothing is sent to n8n until it passes. `get_spec_sheet_data` runs the same check, so n8n stops at its first node whoever started it. The Webflow page is not checked; the template's Webflow Category is required instead. (Owner, 2026-11-03. Rules in Phase 4 "As built".) |
| D79 | The current spec sheet is also attached to the linked Webflow Product; the product's earlier spec sheet attachments are unattached, as on the template. (Owner, 2026-11-03.) |
| D80 | The Webflow Product's Product Category mirrors the template's Webflow Category (Product Category; Tape/Neon: Webflow Category, D54), and its Product Type follows it. The product's `series` mirrors the template's Series. All are read-only on a linked product. `web_product_category` and `web_series` are removed. (Owner, 2026-11-03.) |
| D81 | Spec Gallery: all six templates have a `spec_gallery` table (spec sheets only; nothing goes to the Webflow Product or Webflow). (Owner, 2026-11-04.) |
| D82 | Staging has its own Webflow site, `https://staging-illumenate.webflow.io`, a copy of the main site. The staging ERPNext brand `illumenate` is repointed to it. The staging n8n guard (`[staging]` prefixes, forced hidden, guard checks) is removed for the ilLumenate branch only. 206 keeps its guard until it has its own staging site. Stored Webflow item IDs are remapped on staging. (Owner, 2026-11-04. Details in 10.8.) |
| D83 | Notifications on staging go to the owner only (recipient list in site config). On main, add Kevin back. (Owner, 2026-11-04.) |

### 4.1 Template schema (ship in the app via `web_listing_schema.py`, on the Product Data tab)

Add to all six template doctypes:

| Field | Type | Notes |
|---|---|---|
| `sublabel` | Data | Moves from the product. The product mirrors it. |
| `part_number_builder` | Table | Child doctype `ilL-Child-Webflow-Configurator-Option`, columns unchanged (D25). On the product, `configurator_options` is renamed to `part_number_builder`. **Superseded:** built as `part_no_configurator` (D58); the product table stays for now (D65). |
| `specifications` | Table | Child doctype `ilL-Child-Webflow-Spec-Custom`. Name: `specifications` (D47). Rules: D43. |
| `other_documents` | Table | Replaces the site Custom Field `custom_documents`. Name: `other_documents` (D47). |
| `dimensions_image` | Attach Image | New on the template (D46). The product's existing standard `dimensions_image` is kept as is and mirrors from the template with fallback, so existing product values survive. |
| `web_product_category` | Link (type to confirm) | Replaces the product's `product_category` (D47). **Superseded:** not added (D51, D80). The template's `product_category` (Tape/Neon: `webflow_category`) is the source. |
| `web_series` | Link to `ilL-Attribute-Series` **(verify)** | Replaces the product's `series`, same pattern as the category (D47). **Superseded:** not added (D51, D80). The template's `series` is the source. |
| `target_brands` | Table | Child `ilL-Child-Webflow-Brand-Target`. Source of truth. At most one enabled row at all times (D17), and exactly one is required to generate a spec or to link a product. Kept as a table so the mirror, `trigger_sync_v2` and the per-brand publication state work unchanged. |
| `spec_sheet_public_url` | Data, read-only | The stable URL (4.7). Must be an absolute HTTPS URL (readiness rule on public documents, Appendix C). |
| `review_reason` | on Product Publication | Archive review flag (4.4 item 8). |

Brand pill: a sidebar indicator on the template form, the same pattern as the product's.

**As built (Phases 1a to 4).** All on the Product Data tab of all six templates unless noted, through `web_listing_schema.py` and `tools/stamp_web_listing_fields.py`:

| Field | Type | Notes |
|---|---|---|
| `display_name` | Data | First field of the Product Data section. The product's `product_name` copies it (D64). |
| `sublabel` | Data | |
| `target_brands` | Table `ilL-Child-Webflow-Brand-Target` | At most one enabled row. Exactly one is needed to link a product or make a spec sheet. |
| `dimensions_image` | Attach Image | D46 |
| `certifications` | Table `ilL-Child-Spec-Certification` | D57. Moved from the old place on Tape/Neon, LED Sheet, Driver and Controller (same fieldname, no data move). New on Kit and Fixture. New column `badge_image`: the certification's dark badge for the template's brand, filled on save (`template_images.py`). |
| `spec_sheet_public_url` | Data, read-only | The stable link, set by `register_spec_sheet` (Phase 4). |
| `other_documents` | Table `ilL-Child-Webflow-Document` | |
| `webflow_category` | Link `ilL-Webflow-Category` | Tape/Neon only (D54). |
| `specifications` | Table `ilL-Child-Webflow-Spec-Custom` | Calculated on save (Phase 2). New column `is_calculated` marks rows rebuilt on every save. |
| `part_no_configurator` | Table `ilL-Child-Webflow-Configurator-Option` | D58. Step column hidden and read-only (D67). |
| `auto_populate_configurator` | Check, label "Calculate Configurator on Save", default on | Above the Part No. Configurator. Off: steps set by hand, the save leaves them alone. |
| `spec_gallery` | Table `ilL-Child-Spec-Gallery` | D81. Section, Title, Image. |
| Kit Components `component_image` | Column | Per component type, the first item's template item image (`variant_of`), else the item's own image. |
| Kit Components `component_description` | Column, label Description | Renamed from `webflow_description` (D72). Filled from variant attributes (D73). |

`ilL-Product-Publication` got `review_reason` (read-only, for Phase 5). The child doctypes `ilL-Child-Webflow-Spec-Custom` and `ilL-Child-Comp-Power` existed only on the site; they now ship with the app (fields from the staging export).

### 4.2 Link ownership (D2)

- `template.webflow_product` is the real link. Editable while empty, read-only once set (`read_only_depends_on: eval:doc.webflow_product`). Fill it through the popup (4.5) or an explicit "Link existing product" action. Unlinking is an explicit, permission-checked action.
- The product's per-type link fields (`kit_template` and the others) become **read-only mirrors**, written by template-side code.
- Remove the product's `_update_template_backlink` write to the template (the direction flips). Keep `on_trash` clearing so deleting a product clears the template link.
- Rules: one template links to at most one product, and one product links to exactly one template. Validate both sides. The product's `product_type` must match the template doctype. For `tape_neon_template` the type (LED Tape, COB Tape, LED Neon) must be chosen.
- `webflow_product` is **required when `product_status = Active`**, enforced server-side as well as in the popup.
- Run a consistency report and a data migration for existing records (template backlink and product link must agree).
- **As built:** `template_link.py` and `template_link_report.py` (Phase 1 "As built"). Required-when-Active became required-when-**Active + Live** (D60).

### 4.3 Status model (D1, D32, D33)

Inputs per product and brand:

- `T`: template `product_status` (Draft, Active, Internal Only, Discontinued, Archived)
- `L`: linked product exists (`template.webflow_product` set)
- `P`: published before (Product Publication `published_on` set for that brand)
- `S`: the product's `webflow_status` (human-chosen stage: **Webflow Draft** (default), Publish, Discontinued, Archived). The old stage "Draft" is removed.

Resolution order: **T first, then P, then S.**

| # | T | L | P | S | Effective Webflow action | Public? | Trigger |
|---|---|---|---|---|---|---|---|
| 1 | any | no | n/a | n/a | none (spec only, no product) | n/a | n/a |
| 2 | Draft | yes | no | n/a | none (ERP only) | no | button, spec only |
| 3 | Draft | yes | yes | n/a | hide, review flag, notify (D45) | no | automatic plus notification |
| 4 | Active | yes | no | Webflow Draft (default) | STAGE, hidden-from-public ON | no | automatic |
| 5 | Active | yes | no | Publish | STAGE then PUBLISH, hidden-from-public OFF | yes | human click |
| 6 | Active | yes | no | Discontinued | UNPUBLISH if an item exists, else none | no | automatic |
| 7 | Active | yes | no | Archived | UNPUBLISH and ARCHIVE if an item exists, else none | no | automatic |
| 8 | Active | yes | yes | Webflow Draft | STAGE, hidden-from-public ON (D14) | no | automatic |
| 9 | Active | yes | yes | Publish | PUBLISH (update live) | yes | automatic |
| 10 | Active | yes | yes | Discontinued | PUBLISH, stays public, `is_discontinued` checked (D36) | yes | automatic |
| 11 | Active | yes | yes | Archived | Webflow Draft (STAGE, hidden ON), review flag, notify (D16) | no | automatic plus notification |
| 12 | Internal Only | yes | yes | any | behaves as Discontinued: page stays up (D4). `is_discontinued` checked (D48) | yes | automatic |
| 13 | Internal Only | yes | no | any | none (ERP only) | no | none |
| 14 | Discontinued | yes | yes | any | Discontinued: page stays up until Archived, `is_discontinued` checked (D48) | yes | automatic |
| 15 | Discontinued | yes | no | any | none (ERP only) | no | none |
| 16 | Archived | yes | yes | any | Webflow Draft (hidden), review flag, notify (D16) | no | automatic plus notification |
| 17 | Archived | yes | no | any | none (ERP only) | no | none |
| 18 | Internal Only, Discontinued, Archived | no | n/a | n/a | no product exists, spec only | n/a | n/a |

Notes:

- "Automatic" means a push without a human click, debounced and readiness-gated (D8, 4.4 item 7). Lifecycle status changes (template status or product stage) skip the debounce and push immediately; only field edits wait (D44). Rows 11 and 16 use the archive review flow (4.4 item 8).
- **Row 4** is new behavior (D33): activating and linking a template creates the hidden Webflow draft automatically. Going public always needs a human click (row 5).
- **Re-activation (D5):** when a template moves back to Active from Discontinued or Archived, the product's stage is reset to Webflow Draft. A page that was public is then hidden (row 8, D14). Record the reset in the publication history. Internal Only back to Active resumes the previous stage (D29).
- **Button rule:** the label is **"Generate Spec & Sync to Webflow"** when `L` is true and the effective action is not "none". Otherwise it is **"Generate Spec"**.
- **Changes since this table was written:** read stage "Publish" as "Published" (D49). The "Active" rows 4 to 11 mean **Active + Live**; a plain Active template has no Webflow action (D60). Active + Live back to Active after the product was public: hide and notify (D61). Row 11 now has `is_discontinued` checked (D63).
- **Migration of existing records:** products with the old stage `Draft` need a new stage. Any whose template is Active and linked would be pushed to Webflow as hidden drafts under row 4. Migrate in two steps: run a **dry-run report** of every product that would be pushed (proposed), have the owner review it, then enable pushing (kill switch, 4.4 item 10).
- **Done (Phase 1b, 2026-11-02):** patch `webflow_status_draft_badge_discontinued` moved those products to Webflow Draft. Nothing was pushed, because automatic pushes do not exist yet. The dry-run report and the kill switch are still needed before Phase 5 turns pushes on. Templates meant for the website must also be moved to Active + Live first (`template_link_report.promote_live_templates`, Phase 1 "As built").

### 4.4 Publication pipeline changes (proposed unless marked decided)

1. **Resolver.** New module (proposed `webflow_state.py`) with `resolve_webflow_state(template_doc, product_doc, brand)` returning `{action: NONE|STAGE|PUBLISH|RETIRE, is_draft, is_archived, hidden_from_public, unpublish, archive, is_discontinued, reason}`. This is the single place the table in 4.3 lives (D20). In the staging environment it also forces `hidden_from_public = true` and adds the staging markers (4.11).
2. **Guards in `request()`** use the resolver's `action`, not `payload["active"]`, so Discontinued and Internal Only products can PUBLISH while the template's `is_active` is 0 (Discontinued) or while readiness would otherwise fail. Specifically:
   - The readiness rule "Internal Only templates stay off the website; set the template to Active first" (`product_readiness.evaluate`, channel `cms`) must not fire for the sunset case (row 12). Make it resolver-aware.
   - Keep every other readiness check (Appendix C).
3. **`trigger_sync_v2` picks the operation** from the resolver. NONE returns `{"status": "skipped", "reason": ...}`. STAGE-then-PUBLISH chains the PUBLISH request after the STAGE job completes (in the acknowledge path), because PUBLISH requires the same hash to have been staged.
4. **The job payload carries `webflow_state`** so n8n applies it instead of re-deriving it.
5. **`published_on` backfill:** products that are public today (stage Publish or Discontinued and the last sync succeeded) get `published_on` set, so "published before" is correct from day one.
6. **Effective-state indicator** on the product form: "Effective Webflow state: X (because the template is Y)".
7. **Automatic pushes (D8).** For rows marked automatic: after a relevant save of the template or its linked product, record a due time (now plus the debounce, default 5 minutes, configurable; proposed site config key `spec_auto_push_debounce_minutes`). Each further save resets the timer. A scheduler job (cron, every minute or two) pushes due items. At push time: recompute the effective state, run `inspect()`, and push only if readiness passes. If not ready, skip and notify the last editor. Keep repeated runs idempotent through the existing `request_key`. Lifecycle status changes (template status or product stage) skip the debounce and push immediately; only field edits wait (D44).
8. **Archive review (D16, D30).** When a product that was public (`P`) is archived (rows 11 and 16), do not unpublish or archive it automatically. Set the item to Webflow Draft (STAGE with hidden-from-public ON), set `review_reason` on the Product Publication, and notify once per transition. Show a banner on the template and product forms ("Was public, now hidden pending review"). A **Confirm archive** action (System User, write, role `ilL Catalog Publisher`; records who and when) then runs UNPUBLISH and ARCHIVE. Verify how `live_hash` should read while an item is hidden but still published.
9. **Notifications.** Readiness failures and archive reviews go through one helper (proposed `notify_webflow_alert`) using an ERPNext notification and email. Recipients: the last editor for readiness failures, and a configured list for archive reviews. Initial list: `reigine@illumenate.lighting`, `kevins@illumenate.lighting` (stored in a setting, proposed Single doctype `ilL Webflow Settings`, field `alert_recipients`, not hardcoded). **On staging (D83):** the recipient list lives in site config and holds only the owner while testing. Add Kevin back on main (10.1).
10. **Kill switch (proposed).** Site config `webflow_auto_push_enabled` (default **false** on staging until Phase 5 tests pass). When false, nothing is pushed automatically. The manual button still works.
11. **Status badge automation** is in 4.8.

### 4.5 Spec generation flow (D18)

Orchestration moves into ERPNext. n8n W1 becomes spec-only.

1. Template button (all six doctypes) calls `generate_spec_sheet(template_doctype, template_id)` (proposed). The brand is read from the template's single enabled Target Brand (D17). Block with a message if there is none. The form must be saved first (block with a message if dirty).
2. The method checks permission (4.12), runs as a background job (`frappe.enqueue`), and returns a job id. The form shows progress through the blocking dialog (4.13). The job continues if the user closes the page.
3. The job posts `{template_doctype, template_id, brand}` to W1 with the secret header. The URL comes from site config (proposed key `n8n_spec_webhook_url`), not from code.
4. W1 returns `{success, file_url}` or an error.
5. ERPNext `register_spec_sheet(...)` (proposed) does all the writes: sets `spec_sheet`, updates `spec_sheet_public_url`, mirrors to the product, and prunes older files **after** success (4.7).
6. If the button is the "& Sync" variant and the resolver says the action is not NONE, ERPNext then runs the sync (4.4). `Handoff to Workflow 2` and `Update Webflow?` disappear from W1.

**Popup on status change to Active (D3):** when `product_status` changes to Active and `webflow_product` is empty, show a dialog with Create new, Link existing, Cancel (reverts the status). **One server call** sets the status, creates or links the product, writes both sides and reloads the form (this avoids "modified after you opened it"). For Tape/Neon templates it also asks the product type. A new unsaved template must be saved first. Server-side validation is the backstop.

### 4.6 Payload v2: template and product kept separate (D37, proposed shape)

The data endpoint (proposed `get_spec_sheet_data(template_doctype, template_id)`) returns a structure where every field appears under exactly one owner:

```
{
  "schema_version": 2,
  "context": { "environment": "staging|production", "brand": {...},
               "template_doctype": "...", "template_id": "...", "product": "<name>|null" },
  "template": { identity, sublabel, specifications[], part_number_builder[], kit_components[],
                photometrics, colorimetry, certifications[], compatible_power_supplies[],
                dimensions_image, web_product_category, web_series, other_documents[],
                spec_sheet, spec_sheet_public_url, target_brands[] },
  "product":  null | { name, product_slug, product_type, webflow_status, web_badge,
                       is_discontinued,
                       featured_image, gallery_images[], short_description, is_configurable,
                       documents[] (mirrored), attribute_links[], compatible_products[],
                       category_webflow_item_id, remote_item_id },
  "webflow":  { effective_state: {...}, action, hidden_from_public, environment_marks: {...} },
  "legacy":   { ...the flat shape of today's products[0] under the old key names... }
}
```

Rules:

- `template` holds everything the template owns. `product` holds only what the Webflow product owns (and mirrors are **not** duplicated there).
- **The `legacy` view is an adapter (proposed, DC6).** It re-emits today's flat shape with the old key names (`configurator_options`, `custom_webflow_status`, `custom_dimensions_image_2`, `custom_compatible_power_supplies`, `custom_webflow_description`, and so on). The existing n8n `Format Data to Inject` and `Transform to Webflow Format` nodes and the Vercel generator keep reading it until Phase 9. This is what lets the ERP renames land without breaking n8n (D39).
- Phase 2 deliverable: a field-by-field ownership table (field, owner, new name, legacy key) for owner review.
- Golden test: for at least one kit, one tape and one driver, `legacy` equals today's `get_webflow_products().products[0]` (ignoring key order).

**As built (Phases 2b and 3).** `spec_sheet_data.get_spec_sheet_data(template_doctype, template_id, brand=None)`, whitelisted, read permission on the template. `schema_version` 2 with:

- `context`: environment (site config `illumenate_environment`, else from the site name), brand (the template's enabled Target Brand; any other brand is refused, D71), template doctype and name, product, plus `product_type`, `include_configurator`, `base_url` and `spec_sheet_file_name` (Phase 4).
- `template`: every field and table of the template (it owns them all), including `spec_gallery`.
- `product`: only the fields the Webflow Product owns (ownership table in Phase 2 "As built"). `null` when there is no linked product.
- `webflow`: the product's Webflow Status and its sync state for the brand (the per-brand sync row first, then the older single one). Phase 5 adds the effective state and action.
- `legacy`: always present. With a linked product, exactly what `webflow_export_v2.get_webflow_products(brand, product_slug)` returns, old key names included. Without one, it is built by the same export code (`webflow_export_v2.export_template_record`) on a temporary, unsaved product (Phase 3).
- It runs the spec sheet readiness check and returns an error for a template that is missing anything required (D78). `check_ready=False` is used only by the staging checks.

### 4.7 Spec file URL (decided)

**Changes since this section was written (Phase 4, owner 2026-11-03):** the link and the file name carry the brand (D75), and older files are unattached instead of pruned (D76). The route is a `page_renderer` hook in `spec_sheet_route.py` that returns a 302. The bullets below are the original design; where they differ, Phase 4 "As built" in section 6 is what runs.

- Webflow always sees one **stable public URL per template**: `https://<site>/spec-sheets/<template.name>.pdf`, for example `/spec-sheets/kit-ra01.pdf`. The key is the template **record name** (`template_code`), which does not change. No display-name alias (D6). **This is a redirect route, not a file.** Nothing is ever overwritten at `/spec-sheets/`. The real PDFs stay in Frappe's normal file storage.
- Each regeneration saves a **new file** using Frappe's normal collision handling (a suffix is added when the name already exists). The stable URL redirects to the newest file.
- **File name on disk (D7):** `<template_name>_Spec Sheet.pdf`, for example `Rainier [SF]-6.5ft Extrusion Kit_Spec Sheet.pdf`. No brand prefix. `template_name` is optional on the LED sheet, driver and controller templates, so fall back to the record name when it is empty.
- **Do not port the sanitizing regexes from the old Convert nodes** (4.10). They differ between brands and treat brackets and dots inconsistently. Decide the allowed characters server-side and test that spaces, brackets and dots survive and that the served URL works.
- **Lookup:** the route resolves `<key>` case-insensitively across the six template doctypes (a record named `KIT-RA01` is served at lowercase `kit-ra01`). Zero matches, or more than one, returns a clean 404 and logs. Add a validation or report that no two template doctypes share a record name (case-insensitive).
- **Fields (D19):** `spec_sheet` (Attach) keeps pointing at the current real file so the form shows it. `spec_sheet_public_url` holds the stable URL. The product's `Spec Sheet` document row is built from `spec_sheet_public_url` (fall back to `spec_sheet` if empty).
- **Route requirements:** guest access, a **temporary redirect (302/307)** with `Cache-Control: no-store`, and 404 for an unknown key. The `.pdf` suffix can trip Frappe's static-file handling. Spike S2 decides whether the suffix stays. If it cannot, serve `/spec-sheets/<template.name>` without it. Build the route inside the app (a route rule plus controller, or a `before_request` handler). Claude Code chooses and verifies with `curl -i`. **None of this has been verified yet. Spikes S1 and S2 do that.**
- `/files/<clean>.pdf` interception is **optional** (spike S1), only for backward compatibility with links that already exist.
- **Pruning (D24, superseded by D76):** after the pointer switches, delete older files created by this process for that template. Keep the newest **2**. Never delete the file the pointer references. Never prune after a failed run. Delete through the File document, not by removing the file from disk, because Frappe can reuse one physical file for identical content **(verify)**.
- **Migration:** old files with clean names are on disk, made by the old delete-first workflow (named `<Brand>_<Product>_Spec Sheet.pdf` under `/files/`). For each template, regenerate, repoint Webflow to the stable URL, and remove the old file only after Webflow shows the new link.

### 4.8 Badges (D36, owner decision on Q16 and Q18f)

**As built:** the field is `webflow_badge` (D56) with options blank, New, On Sale, Quick Ship (D50). `is_discontinued` is in `webflow_state.py` and follows D48 plus D63. Migration done by patch `webflow_status_draft_badge_discontinued` (Phase 1b). `product_badge` is hidden and read-only; both exports fill `product_badge` from `webflow_badge`.

- **`web_badge`** (renamed from `custom_web_badge`) is a purely manual Select. The template owns it and the product mirrors it. Options: blank, New, On Sale, Quick Ship, Hide (the same values `product_badge` has today). **No `Discontinued` option is added.** Nothing in ERPNext ever writes to it automatically. Check the options currently on `custom_web_badge` on staging and make them match.
- **`web_badge` replaces `product_badge` entirely (Q18f).** Migration patch: for each product, copy `product_badge` into `web_badge` when `web_badge` is empty. When both are set and differ, do not overwrite: list the conflict in the migration report and stop for the owner. Then hide `product_badge`, and delete it only after nothing reads it (readers: the export, the payload, the legacy adapter).
- **`is_discontinued`** is a read-only Check on the product. Its value comes from the resolver's effective state (D48): checked when `webflow_status` is Discontinued, or when the template is Discontinued with a published product (row 14), or Internal Only with a published product (row 12). Unchecked in every other case, including Archived (rows 11, 16) and anything hidden. It is stored on the product on save, and refreshed by the template's mirror push (D21) whenever the template's status changes, so a template status change updates it without anyone opening the product. It is never edited by hand. It is included in payload v2 (`product.is_discontinued`) and in the `legacy` view.
- **What Webflow receives.** The legacy adapter keeps emitting the old `product_badge` key, now filled from `web_badge`, so the existing Transform node and Webflow's `product-badge` field keep working unchanged. The adapter also emits `is_discontinued` (0 or 1). Until the Webflow-side logic exists (R1), a Discontinued page simply shows its manual badge, if any.
- **R1 (reminder, later work, not in this plan's staging scope):** add the logic in Webflow so that when `is_discontinued` is on, it overrides `web_badge` on the page (for example a Discontinued pill). This needs a Webflow field to carry `is_discontinued` and the n8n node change that sends it (Phase 9). Spike S8 records the Webflow `product-badge` field type now so this is ready when needed.

### 4.9 Converting `custom_` fields to standard fields (D35)

**Why:** fields created through the ERPNext UI (Customize Form) are stored as Custom Field records in the **site database**, not in the app's code. They get the `custom_` prefix. They do not travel with the repo, so staging, production and any new site can differ. Code that depends on them breaks or silently skips (for example `sync_custom_template_data` returns early without `custom_spec_custom`). For doctypes the app owns (`ilL-*`), define fields in the doctype JSON or the schema module so they deploy with the code. Reserve Custom Fields for doctypes the app does not own (for example `Item`).

**Scope:** fields on the app's own `ilL-*` doctypes. For `custom_` fields on core doctypes, list them and ask the owner.

**Procedure (Phase 1b):**

1. Export the full Custom Field list from staging (`frappe.get_all("Custom Field", ...)`). The inventory in Appendix E comes from code references only and is incomplete.
2. For each, compute the new name (drop `custom_`). **On any conflict with an existing field, stop and ask the owner for a name.** Known conflicts are in Appendix E; the Q18 answers are recorded in D46 and D47.
3. Add the field to the doctype JSON or schema module under the new name. Write a patch that copies the data (or renames the column), then deletes the Custom Field record. Register it in `patches.txt`.
4. Update every reader: ERPNext code, client JS, and the list of n8n references (the legacy adapter keeps n8n working until Phase 9).
5. Verify on staging: data preserved, no `custom_` fields left on `ilL-*` doctypes, forms still load.

Order matters. **Do the renames only after the legacy adapter exists (Phase 2)**, because n8n reads `custom_webflow_status` and an unrecognized status becomes public (2.4).

**As built:** the staging export (S5) and the names (D56) are in Phase 0 "As built". The conversion ran in Phase 1b (patches `rename_webflow_product_custom_fields`, then `rename_kit_component_description` and `certification_badge_fields`). The exports keep emitting the old key names for n8n.

### 4.10 n8n changes (staging copy only, sequenced per D39)

**As built:** Z2, Z3 and Z4 are done (Phase 0). In W1 the first node is now Get Spec Sheet Data (a call to `get_spec_sheet_data`, which answers through its error reply when the template is not ready), and the Get Product Info code (kept in the repo as `n8n_workflows/lib/spec_sheet_record.js`) builds the record the Format nodes read from the template, per the owner's mapping (Phase 3). The spec workflow passes the Spec Gallery rows and the TAG.MMDDYY stamp to the sheet. The phase notes do not record each of the other W1 bullets below one by one; check them against the live workflow before promotion (8.2).

**Immediately (Phase 0, not deferred):**

- Z2: assign the correct Webflow credentials to each Webflow node (2.7). Use per-brand nodes or route credentials by brand. Never use the ERP sync credential on a Webflow request.
- Z3: make the `default:` branch of both Transform nodes **fail closed** (hidden, not public).
- Z4: add the staging guards (4.11).

**W1 (spec), when the ERP side is ready (Phase 3):**

- Webhook input becomes `{template_doctype, template_id, brand}`.
- `Get Product Info` becomes a call to `get_spec_sheet_data` and reads the `legacy` view until Phase 9.
- Choose the layout page by template doctype and product type.
- **Delete the orphaned delete-chain nodes in the staging workflow** (`Find Old Specs in ERP`, `Check for Existing Files`, `Split File Array into Individual Items`, `Delete Old Files`, `Re-attach Binary File Stream`). The owner approved deleting them in staging only.
- **Remove the file-name cleanup from both `Convert base64 string` nodes (D11).** Today they build the name from the brand display name plus the product name and strip characters with a regex, and they read `Get Product Info` and the webhook body. Replace them with a plain base64-to-binary conversion. The file name comes from ERPNext (`<template_name>_Spec Sheet.pdf`, 4.7), supplied in the webhook payload or the data endpoint response, and the upload node's `file_name` parameter uses that value.
- Replace `Update Template Spec Sheet` (generic PUT) with a call to `register_spec_sheet`.
- Remove `Update Webflow?`, `Handoff to Workflow 2`, `Job Created?` and the error-branch nodes that existed only for the handoff. Respond with `{success, file_url}`.
- Keep Header Auth on the webhook.

**W2 (sync) and the full node rewrite (Phase 9, deferred):** after ERP templates and products are in good shape, the `Format Data to Inject` and `Transform to Webflow Format` scripts will probably change significantly.

- Transform nodes read `payload.webflow_state` instead of switching on the status.
- Add an **unpublish branch** for `unpublish = true` or `operation = RETIRE` (spike S3 confirms the Webflow call), then PATCH `isArchived` when `archive = true`, then `mark_webflow_synced`.
- Send `web_badge` and `is_discontinued`, the stable spec URL (through `documents-json`) and the renamed fields. The override logic itself is R1.
- Replace the shared `Publish Webflow Item` nodes with per-brand ones.
- Production workflow: ERPNext base URL `app.illumenate.lighting` everywhere (D38).

### 4.11 Staging safety for Webflow (D31, proposed mechanics DC8)

**Changed 2026-11-04 (D82):** staging now has its own ilLumenate Webflow site, `https://staging-illumenate.webflow.io`. For the ilLumenate branch the guard below (prefixes, forced hidden, guard checks) is being removed, and stored item IDs are remapped to the staging site's items instead of cleared (`api/staging_webflow_remap.remap_webflow_ids`). 206 Lighting has no staging site yet and keeps every rule below. Built in Phase 0 (Z4); details there and in 10.8.

Webflow has no separate staging site, and the staging ERPNext likely carries real Webflow item IDs (2.8). A staging sync could modify or unpublish a live item. Required safeguards:

1. **Site config** `webflow_environment` = `staging` or `production` (default `production`). The resolver and payload include it.
2. **Never reuse production item IDs in staging.** One-time script on staging: clear the stored Webflow item IDs and publication state for products so staging creates its own items. Report what was cleared.
3. **Staging items are marked:** name prefixed `[staging] `, slug prefixed `staging-`, and `erp-sync-id` prefixed `staging-`. They are always `hidden-from-public = true`, enforced in the resolver **and** in the staging n8n Transform nodes (defense in depth). They may be published (hidden).
4. **n8n guard:** before any PATCH, publish or unpublish in the staging workflow, GET the item and abort unless its name starts with `[staging]`.
5. Category and other **reference** fields may point at real records (read-only references).
6. Show a visible "Staging: Webflow writes go to [staging] items only" banner on the forms.

### 4.12 Permissions and configuration

- Generalize `_require_product_access` into a template-aware check: **System User, plus write on the template, plus the `catalog` capability** (role `ilL Catalog Publisher`; System Manager also passes, as in `staff.py`) (D28). Apply to: generate spec, sync, create product from template, link and unlink, confirm archive, and (read) history.
- The n8n API user (`webflow-marketing-api@...`) runs `upload_spec_pdf`, `register_spec_sheet`, `mark_webflow_synced` and today `trigger_sync_v2`. It needs System User, the write access, role `ilL Integration` (for `claim` and `acknowledge`) and, wherever `request()` is called as that user, `ilL Catalog Publisher`. Verify on staging with the Permitted Documents report.
- Site config keys (names only): `n8n_sync_secret` (exists), `webflow_environment`, `webflow_auto_push_enabled`, and proposed `n8n_spec_webhook_url`, `n8n_sync_webhook_url`, `spec_auto_push_debounce_minutes`. No hardcoded URLs in code.
- **As built (Phases 0 to 4):** `api/n8n_config.py` reads `n8n_spec_webhook_url`, `n8n_sync_webhook_url`, `n8n_sync_secret` (falling back to the old key `ERP-Sync-Secret-2026`) and `n8n_sync_secret_header` (default `ERP-Sync-Secret-2026`). Other keys in use: `webflow_environment`, `illumenate_environment`, `webflow_enrichment_debug` (Phase 2), `web_listing_legacy_read` (Phase 2c), `spec_sheet_template_sites` (Phase 4), and the staging notification recipient list (D83). `webflow_auto_push_enabled` and `spec_auto_push_debounce_minutes` arrive with Phase 5.
- **As built:** the D28 check is applied to linking and unlinking (`template_link.py`), `spec_sheet_job.generate_spec_sheet` and `template_listing.apply_calculations`.

### 4.13 UI: blocking progress dialog (D40)

**Spike S7 result (Phase 0):** confirmed from Frappe `version-16` source (`frappe/public/js/frappe/dom.js`, `frappe/public/scss/desk/global.scss`). `frappe.dom.freeze(msg)` renders the message inside `<div id="freeze" class="modal-backdrop fade">`, and `#freeze.in { opacity: 0.8; }` caps every child at 80% opacity. The app's override `.freeze { background-color: rgba(0,0,0,0.75) … }` targets a class that does not exist on that element (it has an id `freeze`), so it changes nothing. **As built (Phase 3):** the Generate Spec dialog in `public/js/template_spec_sheet.js` (opaque, no close button). The Sync to Webflow button on the product still uses `frappe.dom.freeze` (8.2).

**Problem found:** the "Syncing to Webflow" box uses `frappe.dom.freeze(msg)` with an app style `.freeze { background-color: rgba(0,0,0,0.75); backdrop-filter: blur(3px); }`. Frappe renders the message inside the `.freeze` overlay element, so the message box inherits the overlay's translucency (likely, **verify**), and the form shows through it.

**Change:** one shared helper (proposed `public/js/ill_busy_dialog.js`) used by **Generate Spec, Generate Spec & Sync to Webflow, and Sync to Webflow**. It shows a modal where the dim backdrop and the message card are **siblings**: backdrop dimmed, card fully opaque (solid background, opacity 1), above the form. It is not dismissible while the job runs. It shows the title, the current step, elapsed time, and on completion a result with a link or an error with a copyable detail.

Messages (my wording, change freely):

| Button | Title | Body |
|---|---|---|
| Generate Spec | Generating spec sheet | Building the PDF for this template. This usually takes about a minute. Please keep this page open. |
| Generate Spec & Sync to Webflow | Generating spec sheet and syncing to Webflow | Step 1 of 2: building the PDF. Step 2 of 2: sending the changes to Webflow. This can take a few minutes. Please keep this page open. The page unlocks when both steps finish. |
| Sync to Webflow | Syncing to Webflow | Sending this product's latest data to Webflow. This can take a few minutes. Please keep this page open. |

Result messages: "Spec sheet ready" with the link, "Synced to Webflow", and on failure "Something went wrong" with the reason and the next step (for example "Fix the issues listed, then try again").

Other UI work: the Create-product popup (4.5), the template brand pill, the effective-state indicator on the product, the Publication History section (4.14), and the archive review banner with the Confirm archive action (4.4).

### 4.14 Publication History view (D12)

A read-only "Publication History" section on the template and the product, listing `ilL-Publish-Job` rows for that product (operation, state, requested by, completed on, last error, brand), plus the Product Publication summary (state, staged on, published on, review reason). Use a whitelisted, permission-checked method. No new table.

### 4.15 Target Brands as a mirror (D10, D17, D22, D26, D27)

- Template `target_brands` is the source. The product's `target_brands` becomes a read-only mirror written by the same sync function as the other mirrors.
- `Component` and `Accessory` products keep their own editable Target Brands (D26).
- Changing a template's brand is blocked once its product has been published on the old brand (D27).
- **As built:** the template's `target_brands` exists and its rules are enforced (Phase 1a). The product's brand rows do not mirror it yet; that comes later (D68, 8.2).

---

## 5. Design choices

**Accepted by the owner (now D18 to D22):** ERPNext orchestrates and W1 is spec-only; `spec_sheet_public_url`; the resolver; template-to-product mirror with fallback; one-row `target_brands` table.

**Proposed, needing the owner's OK:**

| ID | Proposal |
|---|---|
| DC6 | The payload v2 `legacy` adapter keeps old key names so n8n and Vercel keep working until Phase 9 (4.6). |
| DC7 | **Replaced by the owner's Q16 decision (D36, 4.8):** manual `web_badge` stays untouched, plus a read-only `is_discontinued` checkbox. No effective-badge computation. |
| DC8 | The staging safety mechanics in 4.11. |
| DC9 | The kill switch `webflow_auto_push_enabled` and the dry-run report before enabling pushes (4.3, 4.4). |

---

## 6. Phased work

### Phase 0: Quick fixes and spikes (staging only)

**Quick fixes first:**

| Task | What |
|---|---|
| Z1 | Read the n8n webhook URLs and the secret from site config (remove the five hardcoded production URLs). Staging config: `staging-generate-spec-sheet` and `staging-product-sync-v2`. Verify `enqueue_n8n_webhook` sends the shared-secret header. |
| Z2 | Fix the staging Webflow credentials (4.10). |
| Z3 | Make the Transform `default:` fail closed in the staging workflow. |
| Z4 | Staging safety guards (4.11), including the one-time ID clearing. |

**Spikes:**

| Spike | Question | Method |
|---|---|---|
| S1 | Does a request for a missing `/files/...` path reach Frappe, and is a redirect rule honored there? | Appendix B. |
| S2 | Does `/spec-sheets/<name>.pdf` work as a dynamic route (guest, 302/307, no-store, 404 for unknown)? | Prototype a route and `curl -i`. Try without the suffix if the suffix misroutes. |
| S3 | Which Webflow Data API v2 calls unpublish a live item and archive it? | Read Webflow docs. I believe unpublish is a DELETE on the item's `/live` endpoint (verify). |
| S4 | Confirm the readiness and guard behavior in Appendix C against the running code. | Run `inspect()` on sample products. |
| S5 | Which site Custom Fields exist on staging (and production) for `ilL-*` doctypes? | Export the Custom Field list (4.9 step 1). |
| S6 | Does the staging site carry production Webflow item IDs? | Query the sync-state and publication tables. |
| S7 | Confirm the freeze overlay cause (4.13). | Inspect the DOM and CSS. |
| S8 | What type is Webflow's `product-badge` field, and is there a field that could carry `is_discontinued`? | Record the field type and options in the Webflow collection. Information for R1 only. Change nothing. |

**Done when:** each fix is verified, each spike has a written result and a decision.

**Status:** done (2026-10-31). S1 and S2 were folded into Phase 4. S8 is information only and still open (8.2).

#### Phase 0: As built

Scope: the `staging` branch and the staging n8n workflow `NW0NxiyqKyeVrkOJ` only. Production workflow `dvCvIpVLwzjgwccF` was read, not changed. Base: `staging` at `d0f760f`.

**Z1: n8n URLs and secret from site config (app code).**

- New module `api/n8n_config.py`. No n8n URL is hardcoded anywhere in the app any more.
- `trigger_sync_v2` and `trigger_publish_v2` read `n8n_sync_webhook_url`. `request_spec_sheet` reads `n8n_spec_webhook_url`. A missing or non-HTTPS value stops the call with a clear message. There is deliberately no default, so a site without config can never fall back to production n8n.
- The triggers check the URL and secret **before** any publish job is requested, so a misconfigured site fails with no side effects.
- `enqueue_n8n_webhook` now sends the shared-secret header (2.8 item 9). It reads the secret from site config when the worker runs, so the secret never travels through the job queue.
- Secret: `n8n_sync_secret`, falling back to the existing key `ERP-Sync-Secret-2026` so production keeps working until its config is renamed. Header name: `n8n_sync_secret_header`, default `ERP-Sync-Secret-2026` (the header production has always used).
- Verified finding: the **production** W2 webhook also requires Header Auth ("ERP Sync Secret"), and `enqueue_n8n_webhook` sent no header before this change, so production syncs dispatched through it would be rejected by n8n.
- Tests: `tests/portal_unit/test_n8n_config.py` (runs without a bench) and the updated webhook tests in `api/test_deploy_regressions.py` (bench), which assert the header and the configured URL.

Staging site config needed before testing (names only, values from the owner):

| Key | Staging value |
|---|---|
| `n8n_spec_webhook_url` | `https://illumenatelighting.app.n8n.cloud/webhook/staging-generate-spec-sheet` |
| `n8n_sync_webhook_url` | `https://illumenatelighting.app.n8n.cloud/webhook/staging-product-sync-v2` |
| `n8n_sync_secret` | the value of the n8n credential "STAGING Sync Secret" |
| `n8n_sync_secret_header` | `STAGING-Sync-Secret` |
| `webflow_environment` | `staging` |

Promotion note: production must get `n8n_spec_webhook_url` and `n8n_sync_webhook_url` (and ideally `n8n_sync_secret`) before this code reaches `main`, or the spec and sync buttons stop with "not configured". That is the intended fail-closed behavior (10.2).

**Z2: staging Webflow credentials (n8n).** Published as staging version `c7764155-3e7f-46f2-8b30-e7c0b8245384`. A backup of the workflow JSON was taken before editing (the previous active version `a9edd1df-6523-40a7-b422-95f77d92abe9` is also in the n8n version history).

| Node | Before | After |
|---|---|---|
| `(ilL) Webflow: Create Product`, `(ilL) Webflow: Update Product` | Header Auth "ERP Sync Secret" | Header Auth "Webflow ilLumenate" |
| `(206) Webflow: Create Product`, `(206) Webflow: Update Product` | Header Auth "ERP Sync Secret" (+ `Bearer null` on Create) | Header Auth "Webflow 206"; `Bearer null` header removed |
| `Publish Webflow Item (Update)` (shared) | no credential, `Bearer null` | split into `(ilL)` and `(206) Publish Webflow Item (Update)` behind `Brand: Publish (Update)` |
| `Publish Webflow Item (New)` (shared) | "Webflow 206 Prod" + `Bearer null` | split into `(ilL)` and `(206) Publish Webflow Item (New)` behind `Brand: Publish (New)` |

These are the same per-brand credentials the production draft uses on its create and update nodes. No Webflow node uses the ERP credential any more.

ERP secret exposure: the staging workflow had **no recorded executions**, so as far as n8n's history shows, no staging run reached the four nodes that would have sent the "ERP Sync Secret" header to Webflow. Execution data can be pruned, so rotating that secret is still the safe choice (10.1).

Two existing W2 bugs fixed on the way (both would have broken staging tests):

- `Should Publish? (New)` compared the booleans `isDraft` and `isArchived` to the string `"false"` under strict type validation. It now uses the same boolean check as `Should Publish? (Update)`.
- Both `Respond to ilL-Publication-Job` callbacks sent `webflow_item_id: $json.id`, which after a publish is the publish response (no `id`). A newly created item would then have been acknowledged with no item ID and failed. They now read the ID from the create or update response.

**Z3: fail-closed `default:` (n8n).** Both Transform nodes: the `default:` branch now sets `hidden-from-public = true`. Any unknown, empty or renamed status is hidden. Checked with a local harness against the exact node code: Draft, Webflow Draft, Publish, Discontinued, Archived, empty, a typo and a missing key.

**Z4: staging safety guards (n8n and app; one-time reset run on staging 2026-10-31).**

n8n (staging workflow only):

- Transform nodes: every item is `hidden-from-public = true` whatever the status; name prefixed `[staging] `, slug and `erp-sync-id` prefixed `staging-`. The ERP product slug sent back in the callback is unchanged, so `mark_webflow_synced` still finds the product.
- Before every PATCH: `(ilL|206) Staging Guard: Get Item` reads the item from Webflow and `Staging Guard: Check Item` aborts unless its name starts with `[staging]` (test 31).
- Before every publish: `Staging Guard: Before Publish (Update|New)` aborts unless the item's name starts with `[staging]` and `hidden-from-public` is on.
- W2 has no unpublish step yet (Phase 9). When it is added, it needs the same guard (for 206, D82).
- **Changed 2026-11-04 (D82):** this guard is being removed for the ilLumenate branch, which now writes to its own staging site. 206 keeps it.

App:

- `api/staging_webflow_reset.py::clear_production_webflow_ids` (4.11 item 2). It refuses to run unless `webflow_environment` is `staging`, requires System Manager, and is a dry run unless `dry_run=False`. It clears product item IDs (`ilL-Product-Publication` remote ID, staged and live hashes and dates, the product `sync_targets` rows and the legacy `webflow_item_id`) and marks open publish jobs SUPERSEDED. Categories keep their IDs (4.11 item 5). It returns a report of every ID it cleared.
- Staging banner on the `ilL-Webflow-Product` form (4.11 item 6), driven by `webflow_environment`. Template forms get it with the Phase 6 UI work.

Run on staging (after deploying and setting `webflow_environment = staging`):

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.api.staging_webflow_reset.clear_production_webflow_ids
```

Review the dry-run report (it is also the S6 answer), then:

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.api.staging_webflow_reset.clear_production_webflow_ids --kwargs "{'dry_run': False}"
```

Result (2026-10-31, run by the owner on staging): the dry run found production Webflow item IDs on 112 products (product field and brand sync row) and on 4 publication records (`kit-ra01`, `kit-ra02`, `kit-az01`, `lil-sw-led`), and no open publish jobs. That answers S6: yes, staging carried production item IDs. The reset was then applied, and a second dry run reported 0 in every category. The owner kept the first dry-run report as the record of the cleared IDs. Staging syncs then created new hidden `[staging]` items. (Since 2026-11-04 the ilLumenate IDs are remapped to the staging Webflow site instead, D82 and 10.8.)

**Spikes.** The cloud environment that ran this work could not reach `stagingillumenate.v.frappe.cloud`, the Webflow API, or `developers.webflow.com` (network policy). Spikes that needed them were marked blocked, with the commands to run.

| Spike | Status | Result / decision |
|---|---|---|
| S1 `/files/` interception | Blocked (no access to staging) | Run Appendix B. Build `/spec-sheets/` either way. Not run yet (8.2). |
| S2 `/spec-sheets/<name>.pdf` route | Blocked | Folded into Phase 4 (route built; checks in Phase 4 "As built"). |
| S3 Webflow unpublish and archive | Done (docs) | See below. |
| S4 readiness and guards | Done (partly) | Readiness checks confirmed; the `request()` guards and the Internal Only rule were not exercised. |
| S5 Custom Fields on `ilL-*` | Done (staging) | See below. Raised a promotion blocker and owner questions for Phase 1b (answered, D49 to D57). |
| S6 production item IDs on staging | Done | Yes: 112 products and 4 publications carried production IDs. Cleared on staging (Z4). |
| S7 freeze overlay | Done (Frappe v16 source) | See 4.13. The Phase 3 helper renders the backdrop and the card as siblings, not `frappe.dom.freeze`. Optional live check: open the product, click Sync, and inspect `#freeze` in DevTools. |
| S8 Webflow `product-badge` field | Blocked (no Webflow access) | Owner reads it in the Webflow Designer (collection settings) or via `GET /v2/collections/{id}`. Information only (8.2). |

**S3: Webflow Data API v2.**

- Unpublish one item: `DELETE https://api.webflow.com/v2/collections/{collection_id}/items/{item_id}/live`. It removes the item from the live site and sets `isDraft = true` on the staged item. Scope `CMS:write`. Optional `cmsLocaleId`; without it only the primary locale is unpublished.
- Unpublish in bulk: `DELETE https://api.webflow.com/v2/collections/{collection_id}/items/live`, up to 100 items.
- Archive: `PATCH https://api.webflow.com/v2/collections/{collection_id}/items/{item_id}` with `{"isArchived": true}` (the staged-item update the workflow already uses). This part is from prior knowledge of the API, not re-read from the docs; confirm when building the Phase 9 branch.
- Decision for Phase 9: the unpublish branch calls `DELETE .../items/{id}/live` first, then the archive PATCH when `archive = true`, then `mark_webflow_synced`, each behind the staging guard.
- Sources: [Unpublish Single Live Item](https://developers.webflow.com/data/reference/cms/collection-items/live-items/delete-item-live), [Unpublish Live Items](https://developers.webflow.com/data/reference/cms/collection-items/live-items/delete-items-live.md).

**S4: readiness on staging (run by the owner, 2026-10-31, brand `illumenate`).**

| Product | Ready | Issues |
|---|---|---|
| `kit-ra01`, `kit-ra02`, `kit-ra03`, `kit-az01` | yes | none |
| `led-hd-sw` | no | see below |

`led-hd-sw` issues, traced to the code:

- "Dependency graph exceeds preflight bounds" (`product_readiness.dependency_manifest`): the walk of linked records passed 400 records or depth 8 (Appendix C item 21).
- "Source field is absent from the installed schema" (`product_readiness`, spec submittal check): a row in the template's submittal mapping names a source field that does not exist on its source doctype (Appendix C item 15).
- "Enter a finite positive number" twice (`authoring_contract.record_issues`): two numeric engineering values on linked spec records are empty, zero or invalid (Appendix C item 22). For an LED tape spec the checked fields are `watts_per_foot`, `voltage_drop_max_run_length_ft` and, when the tape is not free-cutting, `cut_increment_mm`.
- The console warning "Xref table not zero-indexed" comes from the PDF library reading the submittal PDF. It is not a readiness issue.

Decision: Appendix C matches the running code for the readiness checks. The kits are ready, so kits are the right first staging sync test. `led-hd-sw` needs data fixes before it can sync; that is catalog work, not part of this plan. The Internal Only readiness rule and the `request()` guards (Appendix C items 1 to 5 and 8) were not exercised. They are covered when Phase 5 changes them.

S4 command (`bench --site stagingillumenate.v.frappe.cloud console`):

```python
from illumenate_lighting.illumenate_lighting.api.publication import inspect
for name in frappe.get_all("ilL-Webflow-Product", pluck="name", limit=5):
    r = inspect(name, "illumenate")
    print(name, r["readiness"]["ready"], [i["message"] for i in r["readiness"]["issues"]])
```

`inspect()` needs catalog-reader access (run as Administrator) and is not read-only: it creates or updates the `ilL-Product-Publication` row and its `current_hash`. Leave the console without `frappe.db.commit()` if you want nothing kept.

**S5: Custom Fields on staging (run by the owner, 2026-10-31).**

S5 command:

```python
rows = frappe.get_all("Custom Field", filters={"dt": ["like", "ilL-%"]},
    fields=["dt", "fieldname", "fieldtype", "options", "label"], order_by="dt, fieldname")
for r in rows: print(r.dt, r.fieldname, r.fieldtype, r.options or "", r.label or "", sep=" | ")
other = frappe.get_all("Custom Field", filters={"dt": ["not like", "ilL-%"], "fieldname": ["like", "custom_%"]},
    fields=["dt", "fieldname"])
print(len(other), "custom_ fields on doctypes the app does not own")
```

Run the same on production (read-only) to compare (10.4).

Fields without the `custom_` prefix (the `webflow_item_id`, `webflow_sync_*` and `webflow_sync_targets*` group on the `ilL-Attribute-*` doctypes, and `ill_impact_task`, `ill_next_action_by`, `ill_observed_build_hash`, `ill_review_state` on `ilL-Document-Request`) are created by the app's own patches (`add_webflow_sync_fields_to_attributes`, `migrate_attribute_sync_fields_to_brand_table`, `b2b_conversations`). They deploy with the code, so they are not drift and are out of scope for D35.

`custom_` fields on `ilL-*` doctypes (in scope for Phase 1b):

| Doctype | Field | Type | Notes |
|---|---|---|---|
| ilL-Webflow-Product | `custom_webflow_status` | Select: Draft, Webflow Draft, **Published**, Discontinued, Archived | The option is "Published", not "Publish" (D49). |
| ilL-Webflow-Product | `custom_web_badge` | Select: **None**, New, On Sale, Quick Ship | `product_badge` has blank, New, On Sale, Quick Ship, **Hide**. They differ (D50). |
| ilL-Webflow-Product | `custom_web_product_category` | **Data** | The plan expected a Link. |
| ilL-Webflow-Product | `custom_web_series` | **Data** | The plan expected a Link to `ilL-Attribute-Series`. |
| ilL-Webflow-Product | `custom_spec_custom` | Table (`ilL-Child-Webflow-Spec-Custom`) | Exists on staging, so the template mirror runs there. Production not yet checked. |
| ilL-Webflow-Product | `custom_compatible_power_supplies` | Table (`ilL-Child-Comp-Power`) | |
| ilL-Webflow-Product | `custom_dimensions_image_2` | Attach Image, "Dimensions Image (Dark)" | Deleted per D46 after its values are copied. |
| ilL-Webflow-Product | `custom_template_status` | Data | |
| ilL-Webflow-Product | `custom_min_operating_temp_c_copy` | Int | Deleted (D53). |
| ilL-Webflow-Product | `custom_column_break_lgzvl` | Column Break | Its options held a local Mac file path (a UL badge SVG). Layout only, no data. Deleted (D53). |
| ilL-Tape-Neon-Template | `custom_documents` | Table (`ilL-Child-Webflow-Document`) | Exists on the tape/neon template **only**, not on the other five. |
| ilL-Attribute-Certification | `custom_badge_image_dark`, `custom_206_badge_image_dark`, `custom_206_badge_image_light` | Attach Image | No `custom_badge_image_light`. |
| ilL-Child-Webflow-Certification-Link | `custom_badge_images` | JSON | |
| ilL-Child-Webflow-Kit-Component | `custom_webflow_title` (Data), `custom_webflow_description` (Long Text) | | |
| ilL-Child-Tape-Neon-Allowed-Option | `custom_value_label` | Data | |

That is the 15 names from Appendix E plus `custom_column_break_lgzvl`.

**Finding (promotion blocker, fixed in staging n8n):** the stored status option is "Published", but both Transform nodes, in production as well as staging, only matched "Publish". Published products had therefore been falling into `default:`, which made them public by accident. With the Z3 fail-closed default, promoting the Transform nodes unchanged would have hidden every Published product. Staging version `3ce70f5b-c475-4427-acc2-6981cc8fc86c` adds a `"Published"` case next to `"Publish"`. **Production must get the same case in the same publish as Z3 (10.7).**

Questions put to the owner before Phase 1b (recommendations first), and the answers:

1. `webflow_status` option name: keep "Published" and read the plan's "Publish" as that option. Answer: D49.
2. `web_badge` options: blank, New, On Sale, Quick Ship, Hide, migrate "None" to blank. Answer: D50 (no Hide).
3. `web_product_category` and `web_series` are free text today; make them Links. Answer: D51 (mirror the template's fields, delete the duplicates), and D54, D55.
4. Certification badge names. Answer: D52 (later D74).
5. `custom_min_operating_temp_c_copy`: delete if it holds no data. Answer: D53.
6. `custom_column_break_lgzvl`: delete. Answer: D53.
7. The `custom_` fields on doctypes the app does not own: leave as site Custom Fields. Answer: Q20 (closed, they stay).

D56 mapping (fields deleted by D46, D51 and D53 are not listed):

| Doctype | Current | New |
|---|---|---|
| ilL-Webflow-Product | `custom_webflow_status` | `webflow_status` |
| ilL-Webflow-Product | `custom_web_badge` | `webflow_badge` (replaces `product_badge`, D50 options) |
| ilL-Webflow-Product | `custom_spec_custom` | `webflow_specifications` (the legacy table keeps its name `specifications`, so the D47 rename to `specifications_legacy` is no longer needed) |
| ilL-Webflow-Product | `custom_compatible_power_supplies` | `webflow_compatible_power_supplies` |
| ilL-Webflow-Product | `custom_template_status` | `webflow_template_status` |
| ilL-Tape-Neon-Template | `custom_documents` | `other_documents` (added to all six templates, 4.1) |
| Child of the product: ilL-Child-Webflow-Certification-Link | `custom_badge_images` | `webflow_badge_images` (confirmed) |
| Child of the kit template and the product: ilL-Child-Webflow-Kit-Component | `custom_webflow_title`, `custom_webflow_description` | `webflow_title`, `webflow_description` (same under either rule). Later `webflow_description` became `component_description` (D72). |
| Child of the tape template: ilL-Child-Tape-Neon-Allowed-Option | `custom_value_label` | `value_label` |
| ilL-Attribute-Certification (attribute master, not a product or template) | `custom_badge_image_dark`, `custom_206_badge_image_dark`, `custom_206_badge_image_light` | D52 names at the time; shipped in Phase 3 under the D74 names |

D57 background (verified in code at the time):

- Four templates already had a `certifications` table (child `ilL-Child-Spec-Certification`, one `certification` Link column): Tape/Neon, LED Sheet, Driver and Controller. The Extrusion Kit and Fixture templates had none.
- On product save, `sync_custom_template_data` replaces the product's `certifications` rows (child `ilL-Child-Webflow-Certification-Link`) with the template's.
- `populate_certification_badges` then fills each row's `custom_badge_images` JSON (now `webflow_badge_images`) with the badge image URLs for the product's enabled brands, read from `ilL-Attribute-Certification` (`badge_image` and the dark and 206 badge fields).
- `_populate_certification_attributes` adds each certification to the product's attribute links, and the export builds the `certifications` payload and the "Certifications & Ratings" spec row from the product's rows.
- Found on the way, for Phase 7: the badge URLs use a hardcoded `https://app.illumenate.lighting`, so staging product rows point at production files. It should use the brand's ERPNext base URL (8.2).

Notes on D51 from the code:

- Five templates have `product_category` as a Link to `ilL-Webflow-Category`. The **Tape/Neon template's `product_category` is a Select** (LED Tape, COB Tape, LED Neon): it is the tape family, which readiness compares with the product's `product_type` (`product_readiness.py`, "Template family does not match product"). It is not a category record, so it cannot fill the product's category Link. Hence D54.
- Mirroring onto `product_category` can change the Webflow category of any product whose current value differs from its template's. The Phase 1 migration lists those products first and stops for review (D55).

Custom fields on doctypes the app does not own (staging export, 2026-10-31). The query used `fieldname like 'custom_%'`, where `_` is a one-character wildcard, so it also matched `User Invitation.customer`, which is not a `custom_` field. That leaves 64. They stay as site Custom Fields (Q20).

| Doctype | Fields | Referenced in this repo (code or n8n JSON) |
|---|---|---|
| CRM Lead (Frappe CRM) | 28, including 6 layout breaks/HTML | `custom_campaign` (3 files), `custom_email_activity_log` (1); the rest 0 |
| CRM Deal (Frappe CRM) | 7 address fields and a section break | 0 |
| Email Group Member | 11, including 2 layout | 0 |
| Payment Entry | `custom_qbo_event_type`, `custom_qbo_id`, `custom_qbo_last_synced`, `custom_qbo_sync_note`, `custom_synced_from` | yes (QBO sync) |
| Customer, Supplier, Sales Invoice, Purchase Invoice | `custom_qbo_id`, `custom_synced_from` | yes (QBO sync, 9 and 5 files) |
| Item | `custom_ill_configured_fixture`, `custom_ill_configured_tape_neon` | yes (5 files each) |
| Item Supplier | `custom_supplier_description` | yes (9 files) |
| Company | `custom_invoice_payment_instructions` | yes (3 files) |
| Attendance Request | 1 column break | 0 |

"Referenced 0" only covers this repo. Fields used by n8n workflows that are not exported here, by Webflow forms, print formats, reports or server scripts on the site would also need updating.

Data checks run on staging before Phase 1b (`bench --site stagingillumenate.v.frappe.cloud console`), read-only:

```python
P = "tabilL-Webflow-Product"
for f in ("custom_webflow_status", "custom_web_badge", "product_badge"):
    print(f, frappe.db.sql(f"select `{f}`, count(*) from `{P}` group by `{f}`"))
print("temp copy set:", frappe.db.sql(f"select count(*) from `{P}` where ifnull(custom_min_operating_temp_c_copy, 0) != 0"))
for f, dt in (("custom_web_product_category", "ilL-Webflow-Category"), ("custom_web_series", "ilL-Attribute-Series")):
    vals = frappe.db.sql_list(f"select distinct `{f}` from `{P}` where ifnull(`{f}`, '') != ''")
    print(f, len(vals), "distinct; no matching record:", [v for v in vals if not frappe.db.exists(dt, v)])
```

These are the old field names; after Phase 1b they no longer exist.

### Phase 1: Schema, link ownership, and field conversion

- 1a: add the template fields (4.1) on the Product Data tab through `web_listing_schema.py`. Flip link ownership (4.2). Required-when-Active validation. One-brand validation. Consistency report and migration.
- 1b: convert `custom_` fields to standard fields (4.9). The Q18 answers are in (D46, D47). **Blocked only on Phase 2's adapter existing.** Do 1a first and 1b after Phase 2. Extra steps for `custom_dimensions_image_2`: check for products with a value, copy those to the template's `dimensions_image` (report anything that could not be copied), point the adapter's `custom_dimensions_image_2` key at `dimensions_image`, and only then delete the Custom Field record, on staging only.
- Status changes: remove the stage `Draft` (D33) with the dry-run migration (4.3). `webflow_status` options become Webflow Draft, Publish, Discontinued, Archived. Add the read-only `is_discontinued` checkbox on the product (4.8). Migrate `product_badge` into `web_badge` (4.8).

**Done when:** a template can be linked and unlinked only through the allowed paths. Saving a template and a product in either order never loops. The consistency report is clean on staging data.

**Status:** done. 1a done 2026-10-31. 1b done 2026-11-02, except the product's configurator table rename, which is held (D65).

#### Phase 1a: As built (2026-10-31)

**Template fields** (4.1, D10, D17, D22, D54, D57). The fields are listed in 4.1 "As built". At first they were not mirrored to the product; the mirror (D21) came in Phase 2. Two items were held and then resolved: `part_number_builder` (name conflict, answered by D58) and `specifications` (its child doctype `ilL-Child-Webflow-Spec-Custom`, like `ilL-Child-Comp-Power`, existed only on the site; both now ship with the app).

The name conflict, as put to the owner: the Fixture template already had a `part_number_builder` table (child `ilL-Child-PN-Builder-Row`: section, code, label), read by the spec sheet export and environment codes. D25 wanted the same name for the configurator-option table, a different structure. The owner chose D58. The two site-only child doctypes were exported with:

```bash
bench --site stagingillumenate.v.frappe.cloud execute frappe.client.get --kwargs "{'doctype': 'DocType', 'name': 'ilL-Child-Webflow-Spec-Custom'}"
```

```bash
bench --site stagingillumenate.v.frappe.cloud execute frappe.client.get --kwargs "{'doctype': 'DocType', 'name': 'ilL-Child-Comp-Power'}"
```

**Link ownership** (4.2, D2, D3, D27, D28). New module `template_link.py`, called from each template's `validate`, `on_update` and `on_trash`, and from the product's `validate` and `after_insert`. Desk script `public/js/template_webflow_link.js`.

- `template.webflow_product` is the real link. It is editable while empty and read-only once set.
- The product's six link fields (`kit_template` and the others) are read-only mirrors. Editing one on an existing product is refused. A duplicated product drops the link.
- Creating a product with a template link is allowed (the catalog importer does this, and so will the Phase 6 "Create new" popup) when the template is unlinked, serves the product's type, and the user may change the template. The template side is written on insert.
- Linking from the template (picking the product while the field is empty, or `template_link.link_webflow_product`) checks: the product exists, its type fits the template, neither side is linked elsewhere, the template has exactly one enabled Target Brand, and permission (D28: System User, write on the template, `ilL Catalog Publisher` or System Manager). Then it saves the product with its mirror field set, so the product picks up the template's data in the same request.
- Unlinking only through **Actions > Unlink Webflow Product** on the template (`template_link.unlink_webflow_product`), same permission. Refused while the template is Active + Live (D60; at first, while Active).
- Setting Product Status to **Active + Live** without a Webflow Product is refused (D60; at first this applied to Active, D3). Templates already in that state are listed by the report, not blocked on their next save.
- Target Brands: more than one enabled row is refused (D17). Changing the enabled brand is refused once the product has a `published_on` on the old brand (D27).
- A new template whose record name another template doctype already uses, in any letter case, is refused (4.7, test 26).
- Removed: the product's `_update_template_backlink` (the direction flipped) and `_clear_template_links_for_other_types`. A linked product now cannot change to a type its template does not serve; unlink it first. The product's `on_trash` still clears the template's link.
- No recursion: a product save never saves a template. A template save saves its product only when the link changes, with a flag that skips the product-side check. (Phase 2 added `push_to_product`, which follows the same rule.)

**Consistency report and migration.** `template_link_report.link_consistency_report`, System Manager only, dry run by default. It lists: consistent pairs, template links to fill, product links to fill, template brands to seed from the product, conflicts (two templates on one product, two products on one template, the sides disagreeing, type mismatches), Live templates with no product (`live_without_product`, D60; at first `active_without_product`), ambiguous brands, products whose category or series would change once they mirror the template (D55), and duplicate record names. With `apply` it only fills empty links where both sides agree and seeds a template brand when the product has exactly one enabled brand. It never overwrites a value and runs no save hooks.

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.template_link_report.link_consistency_report
```

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.template_link_report.link_consistency_report --kwargs "{'apply': True}"
```

After deploying to staging: `bench migrate` (the template, product and publication doctypes changed) and a build for `public/js/template_webflow_link.js`. Then the dry run, sent for review.

**First staging report** (dry run): 56 consistent pairs, 10 product links to fill, 55 template brands to seed, 1 conflict, 28 Active templates with no product, 11 brands needing review, 66 category or series differences, no duplicate names. The report was reworked from what it showed:

- A product with no Target Brand rows syncs to the default brand today, so its template is seeded with the default brand instead of being listed for review.
- 62 of the 66 differences were empty template fields. Empty template category, Tape/Neon Webflow Category and series are now **seeded from the product** with `apply` (nothing on the product changes). Only real disagreements stay listed, as `category_series_conflicts`.
- Templates with no link on either side are matched to a free product with the same name (any case) and a fitting type, listed as `suggested_links`, and linked only with `link_suggestions`.
- The conflict entry now shows which product the template itself points at.
- When two products claim a template whose own link points at one of them, `apply` clears the other product's link (`clear_product_link`): the template owns the link (D2). This resolved KIT-RA01 (`ext001-a`).

**Result on staging (2026-10-31).** After `link_suggestions` and two `apply` runs, the dry run reports: 79 consistent pairs; 0 links to fill or clear, 0 brands or categories to seed, 0 suggestions, 0 conflicts, 0 duplicate names. 16 Active templates had no Webflow Product (PS-NON, PS-PRI, PS-WALL, KIT-MS01, KIT-MS13, KIT-MS15, KIT-MS16, KIT-SN03, ILL-CR01-SW, ILL-CR02-FS, ILL-MS13-FS, ILL-TR03-FS, cob-sn-sw, led-sd-cc, non-bst-sw, non-tdr-sw). After D60 these are plain Active and no longer flagged. Phase 1a was done: links change only through the allowed paths, saves do not recurse, and the report is clean apart from owner decisions.

**Tests.** New, bench-free: `tests/portal_unit/test_template_link.py` (18 with the report tests), `test_template_link_report.py`; schema tests in `test_web_listing.py`. Updated: `test_cob_tape.py` (stubs the link module), bench test `test_ill_webflow_product.py::test_fixture_template_link_moves_only_through_the_templates`. The full `tests/portal_unit` suite passed. The bench tests could not be run in that environment.

**Active + Live (D60, 2026-10-31).** Product Status gained Active + Live. It counts as active everywhere Active did: `is_active` is set, dealers see it on the portal (list filters, list permission, document permission, the product finder conditions), and staff see it. The readiness message for Internal Only templates now says to set the template to Active + Live. No data was changed: templates whose product is on the website today were still Active.

Migration (owner): Active templates whose product is Published in Webflow become Active + Live. `template_link_report.promote_live_templates`, System Manager only, dry run by default. "Published" is the product's Webflow Status stage (`webflow_status`, formerly `custom_webflow_status`), value "Published" or the older "Publish"; the publication records' dates were cleared on staging by the Phase 0 reset, so they cannot be used there. Only linked templates change. It also lists, without changing them, templates in another status whose product is Published, and Active templates whose product is Discontinued (still public). Must run before Phase 5's automatic pushes are turned on.

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.template_link_report.promote_live_templates
```

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.template_link_report.promote_live_templates --kwargs "{'apply': True}"
```

#### Phase 1b: As built (2026-11-02)

**`custom_` conversion** (4.9, D35, D46, D53, D56). Patch `rename_webflow_product_custom_fields` (from the commit history; the phase notes only named it in the checklist). It copies every value and row to the new app fields (an existing value in the new field is kept; table rows only change which table they belong to), then deletes the Custom Field records. `custom_dimensions_image_2` is not renamed: its value moves to the linked template's `dimensions_image` when that is empty, and every value that could not move is listed in one Error Log entry (D46). `custom_min_operating_temp_c_copy` and `custom_column_break_lgzvl` are removed (D53). At first `web_product_category`, `web_series` and `webflow_template_status` were kept as read-only copies of the template's Product Category, Series and Product Status; Phase 4 removed `web_product_category` and `web_series` (D80). The export and projection still emit the old key names n8n and the PDF generator read (`custom_webflow_status`, `custom_dimensions_image_2` / `dimensions_image_dark` from the template, `custom_compatible_power_supplies`, kit `custom_webflow_description`).

**Status, badge and Is Discontinued** (4.3, 4.8, D33, D36, D48). Patch `webflow_status_draft_badge_discontinued` (rerun marker in `patches.txt`: "2026-11-02 rerun: Archived and published is discontinued"):

- **Webflow Status:** the stage `Draft` is gone; those products (and any with no stage) are now `Webflow Draft`, the new default. Options: Webflow Draft, Published, Discontinued, Archived. The n8n Transform nodes already treated Draft and Webflow Draft the same, so nothing changes on the website. No automatic pushes exist yet (Phase 5), so nothing is sent to Webflow by this.
- **Badge:** `product_badge` is copied into `webflow_badge` where that is empty. Products whose two badges disagree, or whose old badge is `Hide` (not an option, D50), keep their Web Badge and are listed in the Error Log entry "Product Badge values not moved to Web Badge". The old field is hidden and read-only; both exports now fill `product_badge` from `webflow_badge`, so n8n and Webflow's `product-badge` field read the new value. The field is deleted once nothing reads it (8.2).
- **Is Discontinued** (read-only check on the product, `webflow_state.py`): on when the Webflow Status is Discontinued, or when the template is Discontinued or Internal Only and the product has been published (a publication date, or a Webflow item for any brand), or when the Webflow Status is Archived and the product has been published (D63). Off when the template is Archived, and in every other case. Stored on every product save; a template save saves its product, so a template status change refreshes it. The patch sets the first values. Exported as `is_discontinued` (0 or 1) and in payload v2. Webflow does not use it yet (R1, Phase 9).

**Display Name** (D64, 2026-11-02). All six templates have `display_name` (Product Data tab, first field of the Product Data section). The Webflow Product's `product_name` copies it on every product save, falling back to `template_name` when it is empty; a template save saves its product, so a change shows on the product at once. The spec sheet data (`template` section) carries it.

**Held:** the product's `configurator_options` rename to `part_no_configurator` (D59) is overtaken by D65: the product table stays for now.

### Phase 2: Template-first spec data and payload v2

- Extract the spec-row computation and document mirroring out of `sync_custom_template_data` into functions callable from a template (Appendix D).
- Implement `get_spec_sheet_data` with payload v2 and the `legacy` adapter (4.6).
- Produce the field-by-field ownership table for owner review.
- Golden tests (4.6).

**Done when:** the golden tests pass, including "TBD" rows omitted and a 0 and 0 temperature range omitted (D43).

**Status:** done (2026-11-02). Removing the product's configurator table and product-side calculation (the second 2c push) is held by the owner (D65, 8.2).

#### Phase 2: As built

Done in three pushes so each could be checked on staging:

- **2a**: templates calculate and store their specification rows and configurator steps; products merge in what the template owns; the D43 rules.
- **2b**: `get_spec_sheet_data` (payload v2 with the `legacy` adapter) and the field ownership table.
- **2c**: everything that reads the product's `configurator_options` reads the template's `part_no_configurator` instead (owner, 2026-11-02). Removing the product table was planned as a second push and is held (D65).

**2a: how it works.** The product calculations (`sync_custom_template_data`, the six `populate_*_configurator_options` methods) only read the linked template. They now load it through `_template_doc()`, which returns an in-memory template when one is supplied, and take "Is Required" choices from `flags.existing_is_required` when supplied.

`template_listing.py`:

- `shadow_product(template)`: an unsaved Webflow Product that points at the template being saved.
- `compute(template)`: runs the product code on the shadow and returns its specification rows and configurator steps. Because it is the same code, a template's rows match its product's.
- Template `validate`: `refresh_template` stores the result in `specifications` and `part_no_configurator`. Rows typed on the template (labels that are not calculated) are kept. A calculation error never blocks the save: the old rows stay and the user sees a message.
- Template `on_update`: `push_to_product` saves the linked product (D21). A product that cannot be saved is reported, never blocks the template save. No recursion: product saves never save the template.
- Product `before_save` (end): `apply_template_rows`. The product keeps its own fresh calculated rows (stored template rows can be older than a changed tape spec or attribute record), and takes from the template what people decide there: hand-typed specification rows and each configurator step's "Is Required". Rows typed on the product by hand are kept.

D43, everywhere the calculation runs (template and product):

- A row whose value is the placeholder "TBD" is not added (the driver rows and the LED Sheet "Dimming" row).
- An operating temperature range of 0 to 0 is treated as "not set" and not added (kits and LED sheets; it showed as "32°F (0°C) to 32°F (0°C)").

Also: the calculation wrote an Error Log ("Combined Full Enrichment Debug") on every product save. It now does so only when site config `webflow_enrichment_debug` is set.

**2a: checks on staging.**

1. Deploy. Nothing changes until a template or product is saved.
2. Compare what each linked template would store with what its product holds today (read-only):

   ```python
   import json
   from illumenate_lighting.illumenate_lighting.template_listing import compare_listing
   print(json.dumps(compare_listing(), default=str, indent=1))
   ```

   It compares the template's calculation with the product's own calculation run in memory on today's data (what the product would hold after its next save), not with the product's stored rows, which are often older.

   - `with_unexpected_differences` should be empty. Any difference there is a bug to fix first.
   - `expected_only` counts products whose only differences are the D43 rows.
   - `stale_products`: products whose stored rows are older than their own calculation. They change on their next save whatever the template does. Information only.
   - `hand_curated_configurators`: products with "Auto Populate Configurator Options" off, whose steps were set up by hand. The template never changes them (not even "Is Required"); 2c decides what happens to them.

   The first staging run compared against stored rows, so almost every product showed differences (old number formats, old environment codes, rows never recalculated). That run also showed that hand-set Tape/Neon configurators use different step numbers, so copying the template's "Is Required" by step would have changed the wrong steps. Fixed before any template was saved.
3. Store the rows on every template (products update on their next save):

   ```python
   import json
   from illumenate_lighting.illumenate_lighting.template_listing import refresh_all_templates
   print(json.dumps(refresh_all_templates(apply=True), default=str, indent=1))
   ```

   `failed` lists templates whose save failed, with the reason.

**2a: result on staging (2026-11-02).** `compare_listing`: 82 linked templates, no unexpected differences. 71 products hold stored rows older than their own calculation (they update on their next save); 55 have configurator steps set up by hand. `refresh_all_templates(apply=True)`: 230 templates saved, none failed.

**2b: spec sheet data, payload v2.** `spec_sheet_data.get_spec_sheet_data(template_doctype, template_id, brand=None)`. Shape in 4.6 "As built". At the end of 2b nothing called the endpoint yet. The 2b note expected n8n to move to it in Phase 4; it moved with the Phase 3 work (the Get Spec Sheet Data node and the template mapping, D70). A test fails when a Webflow Product field is added without an owner in the ownership table.

Check on staging (one linked template of each type):

```python
import json
from illumenate_lighting.illumenate_lighting.spec_sheet_data import check_spec_sheet_data
print(json.dumps(check_spec_sheet_data(), default=str, indent=1))
```

Result: `check_spec_sheet_data` with ILL-RA01-DW, cob-fc-sw, BLED-PWM-5C-SF, PS-UNIV, KIT-RA01, led-snf-tw: all built, and `legacy` equals the export for each. This is the golden test (4.6, test 19).

Field ownership (owner review, 2026-11-02, D68). `web_product_category` and `web_series` were removed later (D80).

| Webflow Product field | Owner | Template field | Key in `legacy` | Note |
|---|---|---|---|---|
| `product_name` | Webflow Product |  | `product_name` | Listing name (copied from the template's `display_name`, D64) |
| `product_slug` | Webflow Product |  | `product_slug` | Webflow slug |
| `product_type` | Webflow Product |  | `product_type` | Follows the template's Webflow Category since Phase 4 (D80) |
| `is_active` | Webflow Product |  | `is_active` |  |
| `webflow_status` | Webflow Product |  | `custom_webflow_status` | Webflow Status stage; legacy key custom_webflow_status |
| `webflow_badge` | Webflow Product |  | `webflow_badge` | Badge (D50) |
| `is_configurable` | Webflow Product |  | `is_configurable` | Shows the configurator on the website |
| `configurator_intro_text` | Webflow Product |  | `configurator_intro_text` |  |
| `short_description` | Webflow Product |  | `short_description` |  |
| `features` | Webflow Product |  | `features` |  |
| `featured_image` | Webflow Product |  | `featured_image` |  |
| `series_family_image` | Webflow Product |  | `series_family_image` |  |
| `gallery_images` | Webflow Product |  | `gallery_images` |  |
| `documents` | Webflow Product |  | `documents` | Includes the spec sheet row built from the template (D19) |
| `attribute_links` | Webflow Product |  | `attribute_links` | Calculated on the product from the template's options |
| `compatible_products` | Webflow Product |  | `compatible_products` |  |
| `webflow_compatible_power_supplies` | Webflow Product |  | `custom_compatible_power_supplies` | Calculated on the product; legacy key custom_compatible_power_supplies |
| `driver_spec` | Webflow Product |  | `driver_spec` | Spec link (Driver, Component) |
| `controller_spec` | Webflow Product |  | `controller_spec` | Spec link (Controller) |
| `profile_spec` | Webflow Product |  | `profile_spec` | Spec link (Component) |
| `lens_spec` | Webflow Product |  | `lens_spec` | Spec link (Component) |
| `tape_spec` | Webflow Product |  | `tape_spec` | Spec link (Component) |
| `accessory_spec` | Webflow Product |  | `accessory_spec` | Spec link (Accessory) |
| `portal_item` | Webflow Product |  | `portal_item` | Item sold on the portal |
| `specifications` | Webflow Product |  | `specifications` | Older attribute specification table (deprecated) |
| `product_category` | Template | `product_category` | `product_category` |  |
| `series` | Template | `series` | `series` |  |
| `web_product_category` | Template | `product_category` | `web_product_category` | Removed in Phase 4 (D80) |
| `web_series` | Template | `series` | `web_series` | Removed in Phase 4 (D80) |
| `webflow_template_status` | Template | `product_status` | `webflow_template_status` |  |
| `sublabel` | Template | `sublabel` | `sublabel` |  |
| `dimensions_image` | Template | `dimensions_image` | `custom_dimensions_image_2 / dimensions_image_dark` |  |
| `min_length_mm` | Template | `min_length_mm` | `min_length_mm` |  |
| `max_length_mm` | Template | `max_length_mm` | `max_length_mm` |  |
| `length_increment_mm` | Template | `length_increment_mm` | `length_increment_mm` |  |
| `feed_lengths` | Template | `feed_lengths` | `feed_lengths` |  |
| `kit_components` | Template | `kit_components` | `kit_components` |  |
| `configurator_options` | Template | `part_no_configurator` | `configurator_options` |  |
| `webflow_specifications` | Template | `specifications` | `specifications` |  |
| `certifications` | Template | `certifications` | `certifications` |  |
| `beam_angle` | Template | `beam_angle` | `beam_angle` |  |
| `operating_temp_min_c` | Template | `operating_temp_min_c` | `operating_temp_min_c` |  |
| `operating_temp_max_c` | Template | `operating_temp_max_c` | `operating_temp_max_c` |  |
| `l70_life_hours` | Template | `l70_life_hours` | `l70_life_hours` |  |
| `warranty_years` | Template | `warranty_years` | `warranty_years` |  |
| `fixture_weight_per_foot_grams` | Template | `fixture_weight_per_foot_grams` | `fixture_weight_per_foot_grams` |  |
| `target_brands` | Template | `target_brands` | `target_brands` |  |
| `fixture_template` | Template | `name` | `fixture_template` |  |
| `tape_neon_template` | Template | `name` | `tape_neon_template` |  |
| `controller_template` | Template | `name` | `controller_template` |  |
| `driver_template` | Template | `name` | `driver_template` |  |
| `kit_template` | Template | `name` | `kit_template` |  |
| `led_sheet_template` | Template | `name` | `led_sheet_template` |  |
| `auto_populate_configurator_options` | Not listing data |  | `auto_populate_configurator_options` |  |
| `auto_populate_attributes` | Not listing data |  | `auto_populate_attributes` |  |
| `auto_calculate_specs` | Not listing data |  | `auto_calculate_specs` |  |
| `product_badge` | Not listing data |  | `product_badge` |  |
| `sync_targets` | Not listing data |  | `sync_targets` |  |
| `webflow_item_id` | Not listing data |  | `webflow_item_id` |  |
| `webflow_collection_slug` | Not listing data |  | `webflow_collection_slug` |  |
| `last_synced_at` | Not listing data |  | `last_synced_at` |  |
| `sync_status` | Not listing data |  | `sync_status` |  |
| `sync_error_message` | Not listing data |  | `sync_error_message` |  |

Owner review of the table (2026-11-02):

- `webflow_badge`: stays with the Webflow Product.
- Category and series: the template owns them; the product mirrors them.
- Target Brands: the template owns them; the product's brand rows become a mirror (later).
- Attribute links and compatible power supplies: owned by the product, calculated from the template.
- `documents`: the template owns them (spec sheet and other documents). Left as it is for now; the owner plans to read them straight from the template. Revisit in the cleanup phase.
- Spec links (`driver_spec`, `controller_spec`, `profile_spec`, `lens_spec`, `tape_spec`, `accessory_spec`): the template owns them. Components and Accessories have no template today, so for those the product keeps them until there is one. Revisit in the cleanup phase.
- `is_configurable` (cleanup phase, owner): move it to the template. The dealer portal (Configure button, catalog and product page), the configurator pages (controller list, driver/controller configurator), the product's step calculation, catalog repair and the Catalog Configurability report then read the template's. The product's own check is freed for the owner's other purpose (the Webflow `is-configurable-3` flag is decided then). Not touched now.
- `portal_item` (the Item a dealer adds to a schedule for a one-SKU product such as a kit): left as it is; may be revisited in the cleanup phase.

**2c: readers take the template's configurator.** This push moves every reader to the template and keeps the product table, so staging can be checked against it (and switched back).

Templates: new check **Calculate Configurator on Save** (`auto_populate_configurator`, default on) above the Part No. Configurator. On: the steps are rebuilt on every save (Is Required choices kept). Off: the steps are set up by hand and the save leaves them alone (specifications are still calculated).

Readers: a product linked to a template (the template's Webflow Product points back at it) now reads the template's `part_no_configurator`; a product without a template still reads its own table. The payload key stays `configurator_options`, so n8n and the Webflow scripts do not change.

| Reader | How |
|---|---|
| Webflow export (`webflow_export`, `webflow_export_v2`) | `Listing` reads `configurator_options` from the template |
| Readiness checks (`product_readiness.evaluate`) | same, through `Listing.as_dict` |
| Portal product detail (`product_catalog.get_catalog_product_detail`) | `template_listing.configurator_rows` |
| Product finder facts (`portal/product_finder/facts.py`) | same, one query per template type |
| Catalog Configurability report | same |

Site config `web_listing_legacy_read: 1` sends all of them back to the product's table, as before.

Products: the product's Configurator Options and its Auto-Populate check are read-only once the product is linked to a template, with a note to edit the template. Until each hand-set product is decided (a product with Auto-Populate off whose template still calculates), readers keep showing the product's own steps (`template_listing.pending_decision`), so the website does not change before the owner chooses. Added after the first dry run.

Owner decisions on the first dry run (2026-11-02): Tape/Neon and fixtures with hand-set steps keep them (the narrower fixture choices are deliberate; the Tape/Neon step layout is the one the website uses). The 10 fixtures with no steps take the calculated ones. The goal is still that every template calculates (D66).

Second dry run (2026-11-02): 45 adopted (26 fixtures, 19 Tape/Neon), 10 with no steps take the calculated ones, none failed. It also showed that the hand-set fixture steps still offered the old Environment Rating codes (I, and I/D/O on SH03-SW/TW) instead of 20/54/67, so the website built part numbers with "I", and carried an older output-level lookup (10 entries, 15 calculated). Before a template takes hand-set steps, `refresh_hand_set` brings that data up to date and keeps the choices: old Environment Rating codes become the current ones (I 20, D 54, O 67), and on fixtures the lookup steps 98 and 99 come from the calculation. Each change is listed under `refreshed`. Not changed: Is Required (steps 7 to 11 stay optional on the website, as today).

`template_listing.adopt_hand_set_configurators`, System Manager only, dry run by default:

- `adopted`: templates that take the product's steps, with `same_steps` and each step that differs (`hand_set` next to `calculated`: type / label and how many values).
- `identical`: products whose hand-set steps equal the calculated ones. Nothing changes: their templates keep calculating. For a step whose summary looks the same, `differs` names the fields that differ (`is_required`, `depends_on_step`, `option_description`, allowed values) and `only_hand_set` / `only_calculated` list the allowed values on one side only.
- `empty_on_product`: products with no steps at all (no configurator on the website today). They switch to the calculated steps (owner, 2026-11-02), so they are also listed in `kept_calculated`.
- `kept_calculated`: products named in `use_calculated`. With `apply` their Auto-Populate is turned back on and they show the template's calculated steps.
- `already_hand_set`, `failed`.

2c checks on staging:

1. Deploy and migrate (the six templates and the Webflow Product changed).
2. Dry run, and send the output:

   ```python
   import json
   from illumenate_lighting.illumenate_lighting.template_listing import adopt_hand_set_configurators
   print(json.dumps(adopt_hand_set_configurators(), default=str, indent=1))
   ```

3. Apply, leaving out any product whose template should use the calculated steps:

   ```python
   print(json.dumps(adopt_hand_set_configurators(apply=True, use_calculated=[]), default=str, indent=1))
   ```

4. Compare every export payload with the old path (`[]` means no payload changed):

   ```python
   print(frappe.call("illumenate_lighting.illumenate_lighting.web_listing_source.payload_parity"))
   ```

   Products listed with `configurator_options` are the stale ones from 2a (stored steps older than the template's); anything else listed is a bug.

**2c: result on staging (2026-11-02).** Applied: 45 templates took their products' hand-set steps (26 fixtures with current Environment Rating codes and lookups, 19 Tape/Neon unchanged); the 10 fixtures with no steps (RA01 to RA05 DW, the four RA06, SH03-DW) show the calculated ones. They have no Target Brand, so they are not exported to Webflow until they get one. `payload_parity` lists `configurator_options` only on the 26 fixtures and on 16 products whose stored steps were older than their own calculation (controllers `bled`, `dmxc-rgbtw`, `dmxc-tw`, `dmxd`, not configurable, lose unused leftover rows; kits `kit-az01`, `kit-ch02`, `kit-ra04`, `kit-ra05`, `kit-sh01`, `kit-sh02`, `kit-sh03`, `kit-sl01`; tape `led-snf-sw`, `led-snf-tw`; neon `non-uch-sw`, `non-ucl-sw`).

**What stays (owner, 2026-11-02, D65):** the product's Configurator Options table, its Auto-Populate check and the product-side calculation stay for now, so nothing breaks. They are removed later, after the remaining templates calculate their own steps.

**Catalog import points at the template.** The fixture builder no longer writes placeholder configurator steps onto new Webflow Products (the template calculates them on import), and no longer asks for a step order (`configurator_steps` in older YAML files is read and ignored). In the Catalog Builder the product's Configurator Options and Auto-Populate are read-only, shown only when a record already has them; steps are authored on the template (Part No. Configurator, Calculate Configurator on Save).

**Step order from row order (owner, 2026-11-02, D67).** The Step column is no longer typed: it is hidden from the configurator grid and read-only. On a template whose steps are set up by hand, dragging the rows sets the order; on save the rows take the step numbers already in use, in the new row order (`renumber_steps`). Nothing else is renumbered, so the website sees the same numbers unless a row moved; a new row gets the next free number; lookup steps (98 and up) keep theirs. "Depends on step" and the template's feed lengths follow a moved step. The numbers stay because the website and n8n match steps by number. On a template that calculates its steps, the calculation sets the order.

### Phase 3: Generate Spec endpoint, button and dialog

- `generate_spec_sheet`, `register_spec_sheet`, the background job with status, the dynamic button on all six template doctypes (label from the resolver), the save-first check.
- The blocking dialog (4.13) on all three buttons.
- The minimal W1 changes (4.10) using the adapter.

**Done when:** an unlinked Draft template produces a PDF in `spec_sheet` with no Webflow call and no product created, and the dialog appears and is opaque.

**Status:** done (2026-11-03). The "& Sync" button label and the dialog on the Sync to Webflow button are not built yet (Phase 5, 8.2).

#### Phase 3: As built

**ERPNext.**

- **Generate Spec** button on the six templates (`public/js/template_spec_sheet.js`). The template must be saved first. An opaque dialog with no close button stays open while the job runs and polls its status; the job keeps running if the page is closed. The dialog opens only after the server accepts the job, so a template that fails the readiness check shows only the missing list (from the commit history). Dialog text on completion: "When completed, this page will unfreeze and the new spec will attach to the Spec Sheet field." Phase 5 changes the label to "Generate Spec & Sync to Webflow" when a sync follows.
- `spec_sheet_job.generate_spec_sheet(template_doctype, template_id, brand=None)`: permission as for linking (D28), checks the n8n site config, queues a background job (queue `long`) and returns a job id. `spec_sheet_job_status(job_id)`: Queued, Running, Done or Failed, with a message.
- The job posts `{template_doctype, template_id, brand}` to `n8n_spec_webhook_url` with the shared secret header, waits for `{success, file_url}` (5 minutes), then `register_spec_sheet` checks the template's Spec Sheet points at that file (and sets it if n8n did not). Phase 4 added the stable URL and the file cleanup. Nothing here calls Webflow.
- n8n keeps uploading through `upload_spec_pdf` and then setting the template's `spec_sheet` (D69: that is what fills the File's attached-to fields).

**Data for templates without a Webflow Product.** `get_spec_sheet_data` always has a `legacy` record. With a linked product it is the real export record. Without one it is built by the same export code (`webflow_export_v2.export_template_record`) on a temporary, unsaved product that points at the template and has run the product calculations (spec rows, attribute links, compatible power supplies, certification badges, configurator steps, hero image). The export's per-product code was moved into `_finish_products` so both paths share it.

Keys only a real product fills come out empty in a template-only record (`spec_sheet_data.PRODUCT_ONLY_KEYS`): name and slug, Webflow Status, badge, Is Discontinued, short description, features, featured and series images, gallery, documents, compatible products, configurator intro text, sync fields, Is Configurable, and the spec links.

Staging check: for linked templates, the template-only record compared with the real export, product-only keys left out. `differences` should be empty:

```python
import json
from illumenate_lighting.illumenate_lighting.spec_sheet_data import check_template_records
print(json.dumps(check_template_records(), default=str, indent=1))
```

**Moving the spec workflow off `legacy` (owner, 2026-11-02, D70).** New template columns, filled on every template save (`template_images.py`):

- Kit components `component_image`: per component type, the first item's template item image (`variant_of`), else the item's own image. Example: KIT-RA01, Profile, CH-RA01-SW -> CH-RA01's image.
- Certifications `badge_image`: the linked certification's dark badge for the template's brand (ilLumenate `badge_image_dark`, 206 Lighting `badge_image_dark_206`; at the time `custom_badge_image_dark` and `custom_206_badge_image_dark`).

`context` gains `product_type`, `include_configurator` and `base_url`.

Owner's mapping for the spec workflow (the Get Product Info node, code in `n8n_workflows/lib/spec_sheet_record.js`):

| Spec sheet key | Template source |
|---|---|
| `product_name` | `display_name`, else `template_name` |
| `sublabel` | `sublabel` |
| `featured_image` | `hero_image` |
| `dimensions_image_dark`, `custom_dimensions_image_2` | `dimensions_image` |
| `product_slug` | `template_code`, lowercase |
| `product_type` | `context.product_type` |
| `configurator_options` | `part_no_configurator` (empty when `context.include_configurator` is false) |
| `specifications` | `specifications`: `spec_label`, `spec_value`, `display_order` only |
| `kit_components` | `kit_components` sent as stored; n8n groups them by type: `component_description` = `[{hero_image: component_image}, {code: component_item, label: component_description}...]` |
| `certifications` | `certifications`: `certification`, badge from `badge_image` |
| `photometric_image`, `photometric_data`, `colorimetry` | still `legacy` |
| `custom_compatible_power_supplies` | still `legacy` (product owns it) |

Follow-up (owner, 2026-11-02):

- **Specifications are complete on the template.** The template's calculation also runs the export's enrichment from the linked spec records (`template_listing.linked_spec_rows`: CRI, input voltage, dimensions, dimming, certifications and the like). Those rows are marked `is_calculated` (new column) and rebuilt on every save; rows typed by hand leave it off. The enrichment reads linked records from the database, so a change to the template's own allowed options shows in these rows from the next save.
- **Kit component Description** (new read-only column): the item's Description as plain text, filled on template save. The spec sheet used it as the label next to the item code. (Removed on 2026-11-03, see below.)
- **Brand (D71):** a spec sheet is only made for the template's own Target Brand. A template with no Target Brand, or a request for another brand, is refused (`get_spec_sheet_data`, `generate_spec_sheet`).

Changes (owner, 2026-11-03):

- Kit component `webflow_description` is renamed `component_description` (label Description) on the shared child table, so on template and Webflow Product rows alike (D72). Patch `rename_kit_component_description` copies existing values; the earlier rename patch now copies the old `custom_webflow_description` straight into it. The Webflow export still sends it under `custom_webflow_description`. The read-only item Description column added on 2026-11-02 is removed.
- `get_spec_sheet_data` sends the template's kit component rows as stored; the "Get Product Info" node groups them (labels trimmed, rows kept as they are; the Format node already merges the -NO/-HO endcap pairs), and `(ilL) Format Data to Inject` reads `component_description`.
- Kit templates no longer store the Certifications & Ratings row (`SKIPPED_LINKED_ROWS`); the Webflow export still adds it for kit products.

**Certification badges (owner, 2026-11-03, D74).** `ilL-Attribute-Certification` ships its badge fields: `custom_badge_image_dark` -> `badge_image_dark`, `custom_206_badge_image_light` -> `badge_image_light_206`, `custom_206_badge_image_dark` -> `badge_image_dark_206` (patch `certification_badge_fields` copies values, then deletes the Custom Fields). These three and `badge_image` are Attach fields, so SVG uploads are accepted (Attach Image only takes what the upload dialog treats as images).

### Phase 4: Stable URL and file lifecycle

- Route and redirect (S1, S2 results), `spec_sheet_public_url`, mirror from it, file naming per 4.7, pruning (keep 2), case-insensitive lookup, cross-doctype name check, replace the broken `spec_sheet(product)` endpoint, migration steps.

**Done when:** regenerating a spec keeps the stable URL unchanged and serving the previous PDF until the new one is registered. A failed run never changes the pointer. A guest `curl -i /spec-sheets/kit-ra01.pdf` returns a temporary redirect to the current file.

**Status:** done (2026-11-04). Still open: the recorded S1 and S2 `curl` results, the kit bulk regeneration (the owner runs it later, D77), and the file migration for the other template types (8.2).

#### Phase 4: As built

4.7, with D6, D7, D19 and D24 as changed by D75 and D76. Module `spec_sheet_route.py`.

- **Stable link** per template: `https://<site>/spec-sheets/<brand>_<record name, lowercase>.pdf`, for example `/spec-sheets/illumenate-lighting_kit-ra01.pdf` or `/spec-sheets/206-lighting_kit-ra01.pdf` (D75; first built as `/spec-sheets/<record name>.pdf`, which still resolves). The `.pdf` is optional. The brand part must be the template's own Target Brand, else 404. A redirect, not a file: 302 with `Cache-Control: no-store` to the file the template's Spec Sheet field points at, so the previous PDF is served until the new one is registered. Unknown name, or a name two templates share in any case: 404 (the second is logged). Served by a `page_renderer` hook, which Frappe asks before its own pages and static files.
- **On every successful generation** (`spec_sheet_job.register_spec_sheet`): Spec Sheet points at the new file, `spec_sheet_public_url` is set to the stable link, and the linked Webflow Product is saved so its Spec Sheet document row is the stable link. Older files attached to the template's Spec Sheet field are **unattached, not deleted**; they stay in File Manager (D76; first built as deletion through the File documents, keeping the newest 2 and never the current one). The current spec sheet is also attached to the linked Webflow Product (a second File record for the same stored file), and the product's earlier spec sheet attachments are unattached, as on the template (D79). A failed run changes nothing.
- **File name** (D75; first built per D7 as `<Template Name>_Spec Sheet.pdf`, record name when Template Name is empty, no brand prefix): `<Brand>_<Display Name>_Spec Sheet.pdf` (Display Name, else Template Name, else record name), for example `ilLumenate Lighting_Rainier [SF] Extrusion Kit_Spec Sheet.pdf`. Brand names: `illumenate` ilLumenate Lighting, `lighting_206` 206 Lighting, others their Brand Label. Decided in ERPNext (`context.spec_sheet_file_name` in `get_spec_sheet_data`): spaces, brackets and dots kept; path separators, `: * ? " < > |` and control characters dropped. The per-brand regexes in the old Convert nodes are not used.
- **Unique tag (2026-11-04, from the commit history):** `get_spec_sheet_data` makes a 6-character tag before the PDF is drawn (`spec_sheet_data.spec_sheet_naming`). The stored file is `<Brand>_<Name>_Spec Sheet_<TAG>.pdf`, so Frappe adds no suffix of its own, and the sheet's `#generated-date` reads `<TAG>.<MMDDYY>` (Pacific date). After upload the File Name is set back to the name without the tag, so ERPNext lists it without the tag.
- **`webflow_export_v2.spec_sheet(product)`** (guest): read a product field that does not exist (2.8 item 5); it now redirects through the product's template to its current spec sheet.

**Checks on staging (spikes S1, S2).** After deploying, generate a spec sheet for KIT-RA01, then from any terminal:

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/illumenate-lighting_kit-ra01.pdf
```

Expect `302`, `Cache-Control: no-store` and a `Location` pointing at the current file. Also:

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/206-lighting_kit-ra01.pdf
```

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/no-such-template.pdf
```

The first is a 302 to the current file; the second and third are 404s (KIT-RA01 is an ilLumenate template). The results are not recorded yet (8.2). S1 (`/files/` interception) was not built; it is optional (4.7).

**Bulk regeneration (moving Webflow to the stable links).** `spec_sheet_job.regenerate_spec_sheets`, System Manager only, dry run by default. Active + Live templates unless `statuses` or `templates` say otherwise; templates without a Target Brand are skipped and listed. With `apply`, one background job generates them one after another (one call to n8n and Vercel at a time); one failure does not stop the rest. Each is the same as the Generate Spec button, so each linked Webflow Product's Spec Sheet row becomes the stable link, and Webflow shows it on that product's next sync. Progress: `spec_sheet_bulk_status(bulk_id)` (kept 24 hours). Templates that fail the readiness check are skipped with the reason.

Rollout (owner, 2026-11-03, D77): only the Extrusion Kit spec sheet page exists in Webflow so far, so the bulk run goes one template type at a time (`doctypes="ilL-Extrusion-Kit-Template"`). Other types keep their current spec sheets and links until their Webflow page (`/spec-sheet-templates/<product type>`) is built and that type is regenerated and checked. The dry run's `webflow_pages_needed` lists the pages a run needs.

Not yet (migration, 4.7): repointing Webflow to the stable links and removing the old `<Brand>_<Product>_Spec Sheet.pdf` files once Webflow shows the new links.

**Readiness check (owner, 2026-11-03, D78).** Generate Spec checks the template first (`spec_sheet_check.py`) and lists everything missing; nothing is sent to n8n until it passes. `get_spec_sheet_data` runs the same check and returns an error for a template that is missing anything required, so the spec workflow stops at its first node (Get Spec Sheet Data, which answers through its error reply) whoever started it. The Generate Spec job shows the missing fields from that answer. (`check_ready=False` is used only by the staging checks.)

Required, as it stands after the follow-ups:

- Target Brand, Display Name or Template Name, Sublabel, Hero Image, Dimensions Image, at least one Specifications value.
- The template's Webflow Category (Product Category; Tape/Neon: Webflow Category, D54). The Webflow page is picked from it. (First built as a check that the brand's Webflow page `/spec-sheet-templates/<product type>` exists; the owner dropped that check because not every template has a page.)
- Part No. Configurator: at least one step, each with Option Type, Option Label and Depends On Step.
- Kits: a Default Profile Spec with dimensions, Kit Components rows with Type and Item and a Description on every row, and Operating Temperature Min and Max. An empty Int field reads 0, so "both 0" counts as not set; one bound set and the other empty passes.

Warnings (shown after the spec is generated): rows without Description, certifications without Badge Image, no configurator steps, and Component Images (a warning, not required). Other template types get their own rules when their Webflow page is built.

**The Webflow page comes from the template**, never from the Webflow Product, so templates without a product work. The page lookup uses site config `spec_sheet_template_sites` ({brand code: Webflow site}) when set, else the brand's Webflow Site URL.

**Category, type and series follow the template (owner, 2026-11-03, D80).** The Webflow Product's Product Category mirrors the template's Webflow Category, and its Product Type follows it: extrusions Extrusion Kit, cob-tape COB Tape, controls Controller, landscape and linear-fixtures Fixture Template, led-sheets LED Sheet, led-tape LED Tape, neon LED Neon, power-supplies Driver. The product's `series` (a link to ilL-Attribute-Series, like the template's) mirrors the template's Series on save. All are read-only on a linked product. `web_product_category` and `web_series` are removed (`web_series` was briefly labelled Series before it went).

**Calculation and formatting (owner, 2026-11-03 and 2026-11-04).**

- Environment Ratings are always listed Dry, Damp, Wet (others after, A to Z). The row is labelled "Environment Rating(s)" (the old "Environment Ratings" row is replaced on the next calculation).
- Kit Stock Length and Max Assembled Length use `"` for inches, like Dimensions: `78.7" (2000mm)`.
- Kit Components Description is set on template save from the item's variant attributes (D73): Profile Finish, Lens Lens Color, Endcap Set Endcap Color (attribute names matched in any case). Other types, and items without that attribute, keep the typed Description.

**Template forms (owner, 2026-11-04).** Template sidebar (`public/js/template_sidebar.js`, templates only): brand pill, then the record name, then the Template Name directly under it, as one stacked block at the top like the Webflow Product's. Frappe's own title text is hidden in the title row. **Actions > Apply Calculations** recalculates a saved template on demand (specifications, configurator, component and badge images) and saves its Webflow Product (`template_listing.apply_calculations`, same permission as linking).

**Spec Gallery (owner, 2026-11-04, D81).** All six templates have a **Spec Gallery** section on the Product Data tab (`spec_gallery`, child `ilL-Child-Spec-Gallery`): Section (required; Dimensions, Accessories Dimensions, Bend Diameter(s), Overview, Emission Angle), Title (optional), Image (required, any file type including SVG). Spec sheets only; nothing is copied to the Webflow Product or Webflow. The rows reach n8n in `get_spec_sheet_data` (`template.spec_gallery`) in table order.

ilLumenate kit sheet: the first `.dimension-item` keeps `dimensions_image` in `#spec-dims-img`; `#dimension-item` is repeated once per Dimensions row (title in `#dimension-title`, hidden when empty; image in `#spec-dims-img-other`) and hidden when there are none. The other sections wait for their Webflow pages.

**Kits waiting for data (2026-11-04).** The owner runs the kit bulk regeneration later, once the foundations are set. On 2026-11-04, KIT-RA01 to KIT-RA04 were ready. These were skipped for missing data:

| Kit | Missing |
|---|---|
| KIT-AZ01 | Sublabel, Hero Image, Dimensions Image, Operating Temperature Min and Max |
| KIT-BN03 | Same as KIT-AZ01, plus the Description on Kit Components row 7 |
| KIT-CH02 | Same as KIT-AZ01, plus all Kit Components |
| KIT-RA05 | Hero Image, Dimensions Image, and the Description on Kit Components row 3 |
| KIT-SH01 | Same as KIT-CH02 |
| KIT-SH02 | Same as KIT-CH02 |
| KIT-SH03 | Same as KIT-CH02 |
| KIT-SL01 | Same as KIT-AZ01 |

**Staging Webflow site (2026-11-04, D82).** Not part of Phase 4's scope, but done at the same time: staging got its own ilLumenate Webflow site and the stored IDs were remapped. Details in 10.8.

### Phase 5: Resolver, pipeline, automatic pushes, badges

- `resolve_webflow_state`, `request()` and readiness changes (4.4 items 2 to 4), STAGE-then-PUBLISH chaining, `webflow_state` in the payload, the `published_on` backfill, automatic pushes with debounce, archive review and Confirm archive, notifications, the kill switch, and the `is_discontinued` logic (4.8).

**Done when:** every row of the table in 4.3 has a passing staging test. Rows 10, 12 and 14 must also show `is_discontinued` checked, and rows 11 and 16 unchecked. **Changed by D63:** row 11 (stage Archived, published before) is now checked; row 16 stays unchecked.

**Status:** not started. Built early: the `is_discontinued` logic (`webflow_state.py`, Phase 1b), `review_reason` on `ilL-Product-Publication` (Phase 1a), the Draft-stage migration (Phase 1b). Before automatic pushes are turned on: move templates meant for the website to Active + Live (`promote_live_templates`, Phase 1). Add: the "Generate Spec & Sync to Webflow" label on the template button (D9), the D61 hide-and-notify path, and the opaque dialog on the Sync to Webflow button (D40).

### Phase 6: UI

- Create-product popup, brand pill on templates, effective-state indicator, Publication History view, archive review banner.

**Status:** not started. Built early: the brand pill in the template sidebar (Phase 4), Actions > Unlink Webflow Product (Phase 1a), the staging banner on the Webflow Product form (Phase 0). Still to do: the staging banner on the template forms (Phase 0 Z4).

### Phase 7: Permissions and hardening

- Template-aware permission check on every new endpoint. API user permissions verified. Config keys replace hardcoded URLs. Secret header verified on both ERPNext-to-n8n calls.
- Certification badge URLs use a hardcoded `https://app.illumenate.lighting`, so staging product rows point at production files. Use the brand's ERPNext base URL (found in Phase 0, D57).

**Status:** not started. Built early: config keys replace the hardcoded n8n URLs, and `enqueue_n8n_webhook` sends the secret header (Phase 0 Z1).

### Phase 8: Staging acceptance

- Run the full matrix (section 9).

### Phase 9: n8n node rework (deferred, D39)

- Start only after Phases 1 to 8 are stable. See the W2 and rewrite list in 4.10.
- Unpublish branch: `DELETE .../items/{id}/live`, then the archive PATCH when `archive = true`, then `mark_webflow_synced` (S3, Phase 0). For 206, behind the staging guard while 206 has no staging site (D82).
- **R1:** Webflow-side override of `web_badge` by `is_discontinued` (4.8). Add the Webflow field, send `is_discontinued` from n8n, and build the logic in Webflow.

### Phase 10: Layout and field cleanup (owner, D62)

- After a spec sheet can be generated and Webflow updated end to end, and that has been verified on staging. Go over the templates and the Webflow Product, find the fields that were never used, and clean up layout and fields. The items already queued for it are in 8.2.

---

## 7. Risks

- **Phase 2 is the largest piece of work.** The spec-row logic is a very large method inside the product doctype, and the payload must stay compatible with what the existing n8n nodes expect.
- **Renaming `custom_webflow_status` while n8n still reads the old key** sends every item to the `default:` branch and publishes it. Mitigations: the adapter, fail-closed default (Z3), and doing renames only after the adapter exists.
- **Staging touching live Webflow items** (2.8). Mitigations in 4.11.
- **Recursion** between template save, product save and mirrors (D21).
- **Customer-visible regressions.** Auto-push on live products is debounced and readiness-gated (D8), but an edit that passes readiness and is still wrong goes public after the debounce window.
- **Environment drift** from site Custom Fields (S5).
- **Publishing the production n8n draft early** would start producing changing file URLs (2.7).
- **Template record names** are not guaranteed unique across the six doctypes. The stable URL depends on that (4.7).
- **Migration of old `Draft` products** could push many hidden drafts to Webflow (4.3). Dry-run first.

---

## 8. Open questions (with recommendations)

| ID | Question | Recommendation |
|---|---|---|
| Q22 | Does 206 Lighting get its own staging Webflow site, or does 206 stay guarded on staging? (From the staging-to-main checklist, 2026-11-04.) | Until it has one, 206 keeps the `[staging]` guard (D82). |
| Q23 | Which other n8n workflows (category, series and attribute sync, filter sync) need staging copies, and which move to main as they are? (From the staging-to-main checklist, 2026-11-04.) | Owner to decide. |

### 8.1 Resolved

| ID | Question | Resolution |
|---|---|---|
| Q1 | Stable URL key | `/spec-sheets/<template.name>.pdf`, for example `/spec-sheets/kit-ra01.pdf` (D6) |
| Q2 | "Automatic" pushes | Yes, debounced by a few minutes and only when readiness passes (D8) |
| Q3 | Re-activating an Archived or Discontinued template maps to Webflow Draft, which hides a product that was public. | Return to Webflow Draft and require a human click to go public again. (Agreed in review, D5) |
| Q4 | Cells that were unspecified (Webflow Draft after public, Draft after public, Archived after public) | Hide (D14). The Draft stage no longer exists (D33). Archived after public goes to Webflow Draft with review and notification (D16). |
| Q5 | Component and Accessory products with no template | Keep their own editable Target Brands (D26) |
| Q6 | Changing a template's brand | Block once published on the old brand (D27) |
| Q7 | Specification rows | Keep the rule. Omit "TBD" rows. Treat 0 and 0 as "not set" (D43). |
| Q13 | Lifecycle changes and the debounce | Lifecycle changes push immediately. Field edits are debounced. Retirement is not readiness-gated (D44). |
| Q16 | Badge override | Owner's own design: `web_badge` stays manual, new read-only `is_discontinued` checkbox, Webflow override logic added later (D36, R1). |
| Q17 | Template back to Draft after public | Hide, flag for review and notify, same as Archived (D45). |
| Q18 | Rename conflicts | a, b, d, e approved as recommended (D47). c: `custom_dimensions_image_2` deleted, product `dimensions_image` kept (D46). f: `web_badge` replaces `product_badge` entirely (4.8). |
| Q19 | `is_discontinued` source | Computed from the resolver's effective state, so any page staying up as Discontinued is flagged (D48). |
| Q8 | Part Number Builder | Rename the table fieldname to `part_number_builder`, keep column names (D25) |
| Q9 | Retention of old spec files | Keep the newest 2 (D24) |
| Q10 | Staging Webflow | No separate site. Staging writes `[staging]` items, hidden-from-public always ON (D31) |
| Q11 | Brands per template | One (D17) |
| Q12 | Who may generate and sync | System User, write on the template, role `ilL Catalog Publisher` (D28) |
| Q14 | Internal Only back to Active | Resume the previous stage (D29) |
| Q15 | Archive review | Add Confirm archive. Notify the two recipients (D30) |
| S5 questions 1 to 7 (Phase 0) | Status option name, badge options, category and series, certification badge names, the two odd fields, fields on core doctypes | D49 to D56 and Q20 (Phase 0 "As built") |
| Q20 | Should `custom_` fields on doctypes the app does not own (core and Frappe CRM doctypes) be converted too? | No. The owner did not mean those. They stay as site Custom Fields (closed 2026-10-31). |
| Q21 | An Active + Live template whose product has been published moves back to plain Active | Hide the page and notify the owner; the owner decides the product's Webflow Status (D61). |

### 8.2 Pending and cleanup (from Phases 0 to 4)

This is the one list of open work and cleanup notes recorded during Phases 0 to 4. Promotion steps are in section 10.

**Checks not yet recorded**

- S1 (`/files/` interception, Appendix B) was never run. It is optional; build nothing for it unless old `/files/` links need to keep working.
- S2: the three `curl -sI` checks in Phase 4 "As built" need running on staging and their output recorded here.
- S8: the type of Webflow's `product-badge` field (and a field that could carry `is_discontinued`). Owner reads it in the Webflow Designer or via `GET /v2/collections/{id}`. Information for R1.
- S3: confirm the archive PATCH (`{"isArchived": true}`) against the Webflow docs when building the Phase 9 unpublish branch.
- S4: the Internal Only readiness rule and the `request()` guards (Appendix C items 1 to 5 and 8) were not exercised. Cover them in Phase 5.
- The W1 bullets in 4.10 (delete-chain nodes removed, Convert node file-name cleanup removed, `Update Webflow?` and handoff nodes removed) are not each recorded in the phase notes. Check them against the live staging workflow.
- Phase 3 "Done when" (an unlinked Draft template produces a PDF with no Webflow call and no product created, and the dialog is opaque) is not recorded as checked. The template-only path exists (`export_template_record`).

**Data work (catalog, not code)**

- `led-hd-sw` fails readiness (dependency graph too large, a submittal mapping source field that does not exist, two empty engineering values). Catalog work, not part of this plan.
- Kits waiting for data before the kit bulk regeneration: KIT-AZ01, KIT-BN03, KIT-CH02, KIT-RA05, KIT-SH01, KIT-SH02, KIT-SH03, KIT-SL01 (table in Phase 4 "As built"). The owner runs the kit bulk run later (D77).
- The 10 fixtures with no Target Brand (RA01 to RA05 DW, the four RA06, SH03-DW) are not exported to Webflow until they get one.
- Templates meant for the website must be Active + Live before Phase 5's automatic pushes (`promote_live_templates`).
- Active templates with no Webflow Product (16 on staging after Phase 1a) are fine under D60. The owner links a product and sets Active + Live for any that should be on the website.

**Spec sheet rollout**

- Other template types: their Webflow spec sheet page (`/spec-sheet-templates/<product type>`) must be built, then their own readiness rules added, then that type regenerated and checked (D77).
- The other Spec Gallery sections (Accessories Dimensions, Bend Diameter(s), Overview, Emission Angle) wait for their Webflow pages.
- File migration (4.7): repoint Webflow to the stable links (the bulk regeneration does this per type) and remove the old `<Brand>_<Product>_Spec Sheet.pdf` files once Webflow shows the new links.
- The spec workflow still reads photometric image, photometric data, colorimetry and compatible power supplies from `legacy` (D70).

**Code held or deferred**

- The product's Configurator Options table, its Auto-Populate check and the product-side calculation are removed later, after the remaining templates calculate their own steps (D65). The rename of the product table to `part_no_configurator` (D59) waits for that.
- The 45 templates that adopted hand-set steps are switched back to calculated steps one by one, once their template options match what is sold (D66). Is Required on steps 7 to 11 stays optional on the website for now.
- `product_badge` is hidden and read-only; delete it once nothing reads it (readers: the export, the payload, the legacy adapter).
- The product's Target Brands become a read-only mirror of the template's (later, D68).
- Certification badge URLs use a hardcoded `https://app.illumenate.lighting` (Phase 7).
- The staging banner on the template forms (Phase 6).
- The "Generate Spec & Sync to Webflow" label and the opaque dialog on Sync to Webflow (Phase 5).
- The W2 unpublish step (Phase 9) needs the staging guard for 206 while 206 has no staging site.

**Cleanup phase (owner, 2026-11-02, D62; Phase 10)**

- Go over the templates and the Webflow Product, find fields that were never used, and clean up layout and fields. Until then, layout changes are kept to what the work needs.
- `documents`: the template owns them. The owner plans to read them straight from the template.
- Spec links (`driver_spec`, `controller_spec`, `profile_spec`, `lens_spec`, `tape_spec`, `accessory_spec`): the template owns them; Components and Accessories keep them on the product until they have a template.
- `is_configurable`: move it to the template, and move its readers (dealer portal Configure button, catalog and product page; configurator pages; the product's step calculation; catalog repair; the Catalog Configurability report). The product's own check is freed for the owner's other purpose; the Webflow `is-configurable-3` flag is decided then.
- `portal_item`: may be revisited.

---

## 9. Staging test matrix

| # | Scenario | Expected |
|---|---|---|
| 1 | Unlinked Draft template, Generate Spec | PDF in `spec_sheet`. No Webflow call. No product created. |
| 2 | Unlinked template set to Active | Popup. Create new links both sides. `webflow_product` set. Status saved. Hidden `[staging]` draft appears (auto push enabled). |
| 3 | Popup cancelled | Status reverts. Nothing created. |
| 4 | Linked Draft template, no history | Button says Generate Spec. No sync. |
| 5 | Linked Active, stage Webflow Draft, never published | Item created hidden, name starts `[staging]`. `published_on` empty. |
| 6 | Linked Active, stage Publish, never published, human click | Item published but hidden (staging). `published_on` set by the PUBLISH job. |
| 7 | Regenerate the spec on a live product | Stable URL unchanged. Old PDF served until the new one registers. Old files pruned to the newest 2 afterward. No 404 at any moment (poll during the run). |
| 8 | Failure after upload (force an n8n error) | Pointer not switched. Old URL still serves the previous PDF. |
| 9 | Edit a template field on a published product | Debounced automatic push. |
| 10 | Internal Only on a published product | Item stays up with the Discontinued badge. Readiness does not block it. |
| 11 | Discontinued then Archived on a published product | Stays up, then goes to Webflow Draft (hidden) with the review flag. Owners notified once. |
| 12 | Confirm archive on the item from test 11 | UNPUBLISH and ARCHIVE run. Who and when recorded. |
| 13 | Archived on a never-published product | ERP only. No Webflow action. |
| 14 | Guest `curl -i /spec-sheets/kit-ra01.pdf` | 302/307 with Location. Final 200 PDF. Unknown key gives 404. |
| 15 | Unlink a template | Product mirror link cleared. Guards hold. |
| 16 | Save template then product, and product then template | No recursion. Both complete. |
| 17 | Website User, and System User without write or without `ilL Catalog Publisher` | Denied on every endpoint. |
| 18 | Webhook without the secret header | Rejected by n8n. |
| 19 | Golden payload test (Phase 2) | `legacy` equals old for a kit, a tape and a driver. |
| 20 | `/spec-sheets/KIT-RA01.pdf` and `/spec-sheets/kit-ra01.pdf` | Both resolve to the same file. |
| 21 | Template named `Rainier [SF]-6.5ft Extrusion Kit` | File name keeps spaces, brackets and dots. The served URL works. |
| 22 | Driver, LED sheet or controller template with empty `template_name` | File name falls back to the record name. |
| 23 | Three saves of a published product's template inside the debounce window | One push, after the last save plus the window. |
| 24 | Same, but the product fails readiness | No push. The last editor is notified. |
| 25 | Template moves Archived to Active | Stage resets to Webflow Draft. The product stays hidden until a human click. Reset appears in the history. |
| 26 | Two template records with the same name in different doctypes | Creation blocked. If one exists anyway, the route returns 404 and logs. |
| 27 | Template with two enabled target brands | Save blocked by the one-brand validation. |
| 28 | Generate Spec on a template with no target brand | Blocked with a clear message. No file created. |
| 29 | Renamed status key with the adapter in place | No item changes visibility. An unknown or empty status is hidden (Z3). |
| 30 | Staging sync of a product that had a production item ID | The ID was cleared. A new `[staging]` item is created. No live item is touched. |
| 31 | Staging workflow asked to PATCH an item whose name lacks `[staging]` | Aborts. |
| 32 | Click each of the three buttons | The opaque dialog appears with the right title and body, locks the page, and shows a result. |
| 33 | `webflow_status` set to Discontinued, then changed back | `is_discontinued` becomes checked, then unchecked. `web_badge` is unchanged both times. The checkbox cannot be edited by hand. |
| 33b | Template moved to Discontinued, or Internal Only, with a published product whose stage is still Publish | `is_discontinued` becomes checked without opening the product. Moving the template to Archived or Draft unchecks it. |
| 34 | After Phase 1b | No `custom_` fields remain on `ilL-*` doctypes. Data preserved. |
| 35 | Spec URL against the readiness rule for public documents | Passes (absolute HTTPS URL). |
| 36 | `product_badge` to `web_badge` migration | Empty `web_badge` gets the old value. A product with two different values is reported and left unchanged. `product_badge` is hidden afterward and the legacy `product_badge` key still carries the `web_badge` value. |
| 37 | `custom_dimensions_image_2` removal | Any existing values were copied to the template first. The legacy `custom_dimensions_image_2` key still returns the image. The Custom Field record is gone on staging only. |
| 38 | Template status change (not a field edit) | The push goes out without waiting for the debounce. A field edit made at the same time waits. |
| 39 | Template set back to Draft after its product was public | Item hidden, review flag set, notification sent (D45). |

**Expected results changed by later decisions** (read the rows above with these):

- Tests 2, 5, 6, 30, 31: for ilLumenate, staging now writes to its own Webflow site (D82), so `[staging]` names and forced hidden apply to 206 only once the ilLumenate guard is removed.
- Tests 2, 4 to 11, 25: "Active" means **Active + Live** (D60). "Publish" means "Published" (D49).
- Test 7: older files are unattached, not pruned (D76).
- Tests 14, 20: the link is `/spec-sheets/<brand>_<record name>.pdf` (D75); the form without the brand still resolves. A brand that is not the template's gives 404.
- Tests 21, 22: the file name is `<Brand>_<Display Name>_Spec Sheet.pdf`, falling back to Template Name, then the record name (D75). The stored file also carries a `_<TAG>` suffix; the listed File Name does not (Phase 4).
- Test 28: also blocked by the spec sheet readiness check (D78), which lists every missing field.
- Test 33b: moving the stage to Archived on a published product now checks `is_discontinued` (D63).
- Test 34: names per D56. Test 36: the field is `webflow_badge`; a `product_badge` of "Hide" becomes blank and is listed (D50).
- Test 19: passed on staging (Phase 2, `check_spec_sheet_data`).

---

## 10. Moving from staging to main (promotion checklist)

Owner approval required. Kept up to date as the work goes on (owner, 2026-11-04). Everything below has to be done or checked when the work moves from staging (`stagingillumenate.v.frappe.cloud`, Webflow `staging-illumenate.webflow.io`) to main. Open questions for promotion are Q22 and Q23 (section 8).

### 10.0 Original promotion steps

1. Staging matrix passes. Evidence attached.
2. Back up the production workflow (export JSON, with credentials removed) and note the current published version.
3. Deploy the app branch to production. Run the `published_on` backfill, the link consistency report, and the Draft-stage dry-run review.
4. Apply the n8n changes to production in a single publish.
5. Run the file migration (4.7).
6. Verify the production credentials and tokens, and rotate anything exposed (including the ERP sync secret if it reached Webflow).

### 10.1 Code

- [ ] Merge `staging` into the main branch and deploy, then `bench migrate`. The patches added by the redesign run on migrate: `rename_webflow_product_custom_fields`, `webflow_status_draft_badge_discontinued` (with its rerun marker), `rename_kit_component_description`, `certification_badge_fields`.
- [ ] Build the desk assets (new scripts include `template_webflow_link.js`, `template_spec_sheet.js`, `template_sidebar.js`).
- [ ] CORS list `ALLOWED_ORIGINS` in `illumenate_lighting/utils.py`: keep the main domains; the staging Webflow domains (including `staging-illumenate.webflow.io`) can stay (harmless) or be removed.
- [ ] Notification recipients: on staging they go only to the owner (recipient list in site config, D83). On main, add Kevin back.
- [ ] Rotate the "ERP Sync Secret" (Phase 0 Z2: no staging run was recorded as sending it to Webflow, but execution data can be pruned).

### 10.2 Main site config (`site_config.json`)

- [ ] `n8n_spec_webhook_url` and `n8n_sync_webhook_url`: the production workflow's webhook URLs. Without them the spec and sync buttons stop with "not configured" (intended, Phase 0 Z1).
- [ ] `n8n_sync_secret` and `n8n_sync_secret_header`: the production secret and header name (staging uses `STAGING-Sync-Secret`; the old production header is `ERP-Sync-Secret-2026`, which is also the fallback secret key).
- [ ] `webflow_environment`: `production`.
- [ ] `illumenate_environment`: `production` (or leave unset; it is read from the site name).
- [ ] `spec_sheet_template_sites`: unset, or the main sites, so spec sheet pages come from each brand's Webflow Public Site URL.
- [ ] `webflow_enrichment_debug` and `web_listing_legacy_read`: unset unless needed.
- [ ] The notification recipient list: the owner and Kevin (D30, D83).

### 10.3 Main ERPNext records

- [ ] ilL-Webflow-Brand (each brand): Webflow Site ID, Webflow Public Site URL, ERPNext Base URL Override and every Collections row point at the main Webflow site, not staging. (On staging, brand `illumenate` is being repointed to the staging site, 10.8.)
- [ ] ilL-Webflow-Settings: Site ID and collection IDs, if anything still reads them.
- [ ] Stored Webflow item IDs (products, categories, series, attributes) are main-site IDs. Staging IDs must never be copied to main. Webflow item IDs differ between the sites; they are remapped on staging only (10.8). The product-type Option IDs turned out the same on the copy (remap dry run, 2026-11-04). On main, the main-site IDs must stay.
- [ ] Do not run `staging_webflow_reset.clear_production_webflow_ids` or `staging_webflow_remap.remap_webflow_ids` on main (both refuse unless `webflow_environment` is `staging`).

### 10.4 Data runs on main (dry run first each time)

- [ ] Compare Custom Fields on main with the staging export (Phase 0 S5 command) before migrating, so the Phase 1b patches find what they expect. `custom_spec_custom` was not checked on production.
- [ ] `template_link_report.link_consistency_report` (then `link_suggestions` and `apply` as on staging, Phase 1a).
- [ ] `template_listing.refresh_all_templates(apply=True, push=True)`.
- [ ] `template_listing.adopt_hand_set_configurators` (staging adopted 55: 45 kept hand-set with refreshed codes, 10 empty fixtures switched to calculated), then `web_listing_source.payload_parity`.
- [ ] `template_link_report.promote_live_templates` (Active templates with a published product become Active + Live) before automatic pushes are turned on.
- [ ] `published_on` backfill (Phase 5).
- [ ] Review the "Product Badge values not moved to Web Badge" and `custom_dimensions_image_2` Error Log entries the patches write.
- [ ] `spec_sheet_job.regenerate_spec_sheets` per template type that has a spec sheet page, so every product gets the stable link `/spec-sheets/<brand>_<template>.pdf`.
- [ ] Kits still missing data on 2026-11-04 (KIT-AZ01, KIT-BN03, KIT-CH02, KIT-RA05, KIT-SH01, KIT-SH02, KIT-SH03, KIT-SL01): see Phase 4 "As built" and 8.2.

### 10.5 Webflow (main sites)

- [ ] Spec sheet template pages (`/spec-sheet-templates/<product type>`, e.g. `extrusion-kit`) exist and are published on each brand's site, with the same classes and ids as staging (`#generated-date`, `.cert-icon`, `#dimension-item`, `#dimension-title`, `#spec-dims-img-other`, ...).
- [ ] CMS fields added on staging exist on main with the same slugs (for example the discontinued flag).
- [ ] Spec sheet links in Webflow use the stable links after the bulk regeneration.

### 10.6 n8n

- [ ] Back up the production workflow `dvCvIpVLwzjgwccF` first (10.0 step 2). Its saved draft has unpublished edits (2.7); do not publish them on their own.
- [ ] Production spec and sync workflow replaced by the staging one, with every staging value swapped: ERPNext host `stagingillumenate.v.frappe.cloud` (in HTTP nodes and in the Format and Transform code), webhook paths (`staging-generate-spec-sheet`, `staging-product-sync-v2`), the webhook Header Auth credential, the ERPNext `Authorization` credential, the Webflow credentials for each brand (staging ilLumenate uses `Webflow ilLumenate Staging`; main uses the main-site credential), and the spec template fetch URL.
- [ ] The Transform nodes carry the `"Published"` case next to `"Publish"` in the same publish as the fail-closed `default:` (Phase 0 S5 finding). Without it, every Published product would be hidden.
- [ ] No staging-only logic left: the `[staging]` name and slug prefixes, forced hidden items and the staging guard checks. On staging these are being removed for the ilLumenate branch only; the 206 branch keeps them until 206 has its own staging site (D82, Q22). Remove them from both branches on main.
- [ ] The 206 nodes, including the owner's own stamp edit in `(206) Format Data to Inject`.
- [ ] Execution saving: n8n stores webhook headers, including the secret, in execution data. Limit saving of successful executions or rotate the secret.
- [ ] `n8n_workflows/lib/spec_sheet_record.js` in the repo matches the live Get Product Info node.
- [ ] The one-off `[STAGING] Webflow ID remap` workflow is not copied to main.

### 10.7 Open (**?**)

- **?** Does 206 Lighting get its own staging Webflow site, or does 206 stay guarded on staging? (Q22)
- **?** Which other n8n workflows (category, series and attribute sync, filter sync) need staging copies, and which move to main as they are? (Q23)

### 10.8 Staging setup (as of 2026-11-04)

What staging looks like now, so it is not carried to main by mistake:

- Staging has its own Webflow site, `https://staging-illumenate.webflow.io` (site ID `6aeb4d313e25a078e9393924`, Products collection `6aeb4d313e25a078e9393a2a`), a copy of the main site.
- The staging ERPNext brand `illumenate` is being repointed to it.
- The n8n credential `Webflow ilLumenate Staging` (Header Auth) holds the staging site's token.
- The staging n8n workflow's guard (the `[staging]` prefixes, forced hidden, guard checks) is being removed for the ilLumenate branch only. 206 keeps its guard until it has its own staging site.
- Webflow item IDs differ between the sites (the product-type Option IDs were checked by the remap workflow and are the same on the copy). Item IDs are remapped on staging by `api/staging_webflow_remap.remap_webflow_ids` (staging only, dry run by default). Products are matched to the staging item by `erp-sync-id` (the product name), else by slug; the product's sync row for the brand, its publication record and (default brand) its own Webflow Item ID get the new ID, the staged and live hashes are cleared so the next sync sends a full update, and Published On is the item's last publish date. A product with no match has its stored ID cleared, so its next sync creates a new item. Categories are matched by slug, else by name. The one-off n8n workflow `[STAGING] Webflow ID remap` reads the new site's items and posts them to it. CORS allows `staging-illumenate.webflow.io`. Dry run 2026-11-04: 111 of 113 staging products matched, none had an old ID; 26 ERPNext products are not on the staging site (created on first sync); 7 of 9 categories matched, `cob-tape`/`cob-tapes` and `landscape`/`landscapes` pending the owner's answer; no `[staging]` copies on the main site. The staging workflow's ilLumenate branch (staging credential, staging template fetch, no prefixes or forced hiding, no guard nodes) is saved as a draft, published after the brand record and the remap are applied.
- On main, the main-site IDs must stay, and `spec_sheet_template_sites` should be unset or the main sites.
- Notifications on staging go only to the owner (recipient list in site config). On main, add Kevin back.

---

## 11. Appendix A: How ilL-Publish-Job works (simplified)

1. Every product and brand has one **Product Publication** with a state and four content fingerprints (hashes): what the product looks like now, what someone approved, what is in Webflow staging, what is live.
2. Saving the product changes the current fingerprint, so the earlier approval no longer counts (`NEEDS_REVIEW`).
3. A sync request creates a **job** (STAGE, PUBLISH, or RETIRE) tied to that exact fingerprint and records who approved it. Asking twice for the same content reuses the same job. The Sync button approves the current revision itself.
4. A claim step hands out waiting jobs: outdated ones are marked SUPERSEDED, jobs whose product is not ready are skipped, and a claimed job is leased for 5 minutes. ERPNext then sends it to n8n.
5. n8n does the Webflow work and calls back. The job becomes COMPLETE or FAILED, and the publication's staged or live fingerprint and dates are updated. A retire clears the live and staged fingerprints but keeps `published_on`.
6. If the content changed while a job ran, the callback marks the job SUPERSEDED instead of recording it as live.

In short: a queue with approvals and fingerprints, so only the exact content someone approved reaches Webflow, and stale jobs cannot overwrite newer content.

## 12. Appendix B: Spike S1 commands

Run against **staging**, not production.

```
# 1. Does a missing /files path reach Frappe? Compare the body and headers with a normal Frappe 404 page.
curl -si "https://stagingillumenate.v.frappe.cloud/files/zz-no-such-file.pdf" | head -30

# 2. Add a Route Redirect in Website Settings:
#    source: /files/zz-redirect-test.pdf   target: /   (use a temporary 302 if a status field is offered)
#    Clear the site cache, then:
curl -si "https://stagingillumenate.v.frappe.cloud/files/zz-redirect-test.pdf" | head -20
```

Decision rule: if (1) returns a Frappe-rendered 404 and (2) returns a redirect with a Location header, `/files/` interception is feasible. Otherwise use `/spec-sheets/` only. Build `/spec-sheets/` either way.

## 13. Appendix C: What can make a sync fail (plain language)

Verified against `publication.py`, `product_readiness.py`, `portal/staff.py` at `1d8950f`. The first group stops a sync before it starts. The rest are "readiness" checks. A product is ready only when the issues list is empty.

**Before anything starts (`request()` and `trigger_sync_v2`)**

1. The person lacks the `catalog` capability (role `ilL Catalog Publisher`, or System Manager). Claiming and callbacks need role `ilL Integration`.
2. The product is not "active" for this brand: the product's `is_active` is off, or the brand is inactive, or the product does not target this brand.
3. The brand row in the product's Target Brands is disabled.
4. PUBLISH only: the same revision must already be staged and approved, and the item must already exist in Webflow (`remote_item_id`).
5. RETIRE only: the product must be inactive, and brand sync must be enabled.

**Readiness: product basics**

6. `product_name`, `product_slug` or `product_type` is empty.
7. A configurator choice contains invalid JSON.
8. The linked template's status is **Internal Only** ("Internal Only templates stay off the website; set the template to Active first"). **This conflicts with decision D4 and must change (4.4).**
9. `featured_image` or `short_description` is missing.
10. The featured image is not an approved public image.
11. A row in `documents` is not a public file or an HTTPS URL. The new stable spec URL must be an absolute HTTPS URL to pass this.

**Readiness: template and spec data**

12. A configurable product (or a type with a template mapping) has no family template selected, or the template does not exist.
13. The template has no active compatible specification in its choices table.
14. Tape/neon only: the template family does not match the product category.
15. Configurable products need the **spec submittal PDF template**: a fillable PDF must be attached, not encrypted, with valid field mappings whose source fields exist.
16. Fixture, tape/neon and LED sheet templates: included-power configurations need active compatible driver eligibility.
17. Fixture templates: compatibility coverage must be complete (endcap maps, mounting maps, leader maps, tape offerings, no ambiguous mappings).

**Readiness: everything the product points to**

18. Any referenced record is inactive or disabled ("Referenced record is inactive").
19. A referenced record is missing ("Missing <type>: <name>").
20. An attached file is missing, or a publication file is larger than 20 MiB.
21. The dependency graph is too large, or a record has more than 200 associations.
22. A referenced master record fails its own authoring-contract checks.

**Readiness: brand and category**

23. The brand has no Products collection ID, or brand synchronization is disabled.
24. The product has a category (and it is not a "light type"), but that category has not been synced to this brand yet ("Stage category in this brand first").

**During and after the run**

25. `claim()` skips non-RETIRE jobs while the product is not ready. Jobs for stale revisions are marked SUPERSEDED. A claimed job is leased for 5 minutes.
26. The callback is rejected if the token or hashes do not match.
27. Webflow API errors (bad credential, unknown collection, invalid field values, duplicate slug) fail the n8n run.

**Not verified:** the implementation of the "public file or HTTPS URL" rule (`safe_document_url`) lives outside the files read. Check it when testing the stable URL.

## 14. Appendix D: What the spec calculations do (plain language)

Verified in `sync_custom_template_data` (`ill_webflow_product.py`, line 3335 to the end).

**When it runs:** every time the product is saved, and only if the product has the site Custom Field `custom_spec_custom`.

**What it rebuilds:** rows whose label is in the `MANAGED_LABELS` list are deleted and rebuilt on every save. Rows with any other label (typed by hand) are kept.

**Which rows, by type:** Fixture templates, LED tape and neon, LED sheets, drivers and extrusion kits each have their own branch. I found no branch for controllers **(verify)**.

**Four kinds of work:**

1. **Collect and join (most rows).** Gather the distinct values across the template's linked specs, sort them, and join with commas. Examples: lens options, mounting options, finish options, light color (CCT), CRI, input voltage, dimming, environment ratings.
2. **Convert and format.** Dimensions (millimeters to inches and millimeters, for example `0.55" (14.00mm) x 2.68" (68.00mm)`), stock length, max assembled length, and kit operating temperature (Celsius to Fahrenheit: `round(C x 9/5 + 32)`, shown as `32°F (0°C) to 32°F (0°C)`).
3. **Real arithmetic.** "Max Footage per 100W Supply" = round up (80 divided by watts per foot), for each wattage option, sorted high to low. The label says 100W but the calculation uses 80W (80 percent of a 100W supply). The LED sheet version uses watts per square foot. **(Confirm 80 is intended.)**
4. **Pass-through.** Max Run Length (the voltage-drop max run length from the tape spec), watts per foot, production or cut interval, warranty in years.

**Also:** several driver rows (total harmonic distortion, start-up time, minimum load, max output current, certifications, operating temperature) and the LED sheet dimming row are written as the literal text **"TBD"**.

**Two quirks to know:**

- The kit temperature check only skips a value that is empty or missing, but numeric fields default to 0. A template with unset temperatures therefore shows `32°F (0°C) to 32°F (0°C)`. This is visible on `kit-ms17`.
- Rows are grouped (Electrical, Optical, Physical, Environmental, Control, Performance, Compliance), carry a unit and a display order, and are sorted and re-indexed at the end.

Extrusion kits also build component groups with hero images.

## 15. Appendix E: `custom_` field inventory (from code and n8n references only)

15 distinct `custom_` names are referenced. None is declared in the app. **Export the real Custom Field list from staging first (4.9); it will have more.**

**Superseded (Phase 0 S5, Phase 1b):** the staging export and the final names (D50 to D53, D56, D74) are in Phase 0 "As built". The conversion is done. The "Proposed new name" column below is the original proposal.

| Name | Proposed new name | n8n references | Notes |
|---|---|---|---|
| `custom_webflow_status` | `webflow_status` (owner's choice) | 6 | Stage options change (D33). Drives visibility. |
| `custom_web_badge` | `web_badge` (owner's choice) | 0 | Seen on records, not in repo code. Stays manual. Replaces `product_badge` entirely (Q18f, 4.8). No `Discontinued` option. |
| `custom_web_product_category` | `web_product_category` | 0 | Replaces `product_category`. Approved (D47). |
| `custom_web_series` | `web_series` | 0 | Replaces `series`. Approved (D47). |
| `custom_template_status` | `template_status` | 0 | Mirrored from the template. |
| `custom_spec_custom` | `specifications` | 0 | Legacy table becomes `specifications_legacy`. Approved (D47). |
| `custom_documents` | `other_documents` | 0 | Approved (D47). |
| `custom_dimensions_image_2` | delete (no rename) | 8 | Moves to the template as `dimensions_image`. Product keeps its standard `dimensions_image`. Adapter keeps emitting the old key until Phase 9 (D46). |
| `custom_compatible_power_supplies` | `compatible_power_supplies` | 2 | |
| `custom_webflow_title` | `webflow_title` | 0 | |
| `custom_webflow_description` | `webflow_description` | 2 | Used on kit component rows. |
| `custom_value_label` | `value_label` | 0 | |
| `custom_badge_images` | `badge_images` | 0 | |
| `custom_badge_image_dark` | `badge_image_dark` | 0 | |
| `custom_206_badge_image_dark` / `custom_206_badge_image_light` | `206_badge_image_dark` / `206_badge_image_light` | 0 | A fieldname starting with a digit may be a problem. **Ask the owner for names.** |
| `custom_min_operating_temp_c_copy` | ask | 0 | Seen on records. Odd name ("copy"). Ask the owner. |

Appears on records but not in the repo code, so confirm on staging: `custom_web_badge`, `custom_min_operating_temp_c_copy`.

## 16. Suggested kickoff prompt for Claude Code

Kept for the record. It was the prompt for Phase 0. For later phases, start from section 0 and section 6.

> Read `erpnext_spec_sheet_redesign_plan.md` fully. Work only on the `staging` branch of the ERPNext app, pinned to commit `1d8950f`, and on the staging n8n workflow `NW0NxiyqKyeVrkOJ`. Never touch `main`, production, or any Webflow item that is not marked `[staging]`. Start with Phase 0: do Z1 to Z4, then spikes S1 to S8, and report the results before starting Phase 1. Do not guess on open questions in section 8: stop and ask. Never put secrets in code or commits.

## 17. Version log

- 0.1 (2026-10-31): first draft from the planning conversation.
- 0.2 (2026-10-31): recorded owner decisions (stable URL key, file naming, automatic pushes, re-activation rule, Convert node cleanup, staging node deletion). Added the decision log. Separated `template_id` from `template_name`.
- 0.3 (2026-10-31): recorded Q4 answers and one brand per template. Reworked the status table. Added archive review, notifications, DC5, Q15 and tests.
- 0.4 (2026-10-31): consolidated rewrite. Pinned to the `staging` branch at commit `1d8950f`. Recorded Q5, Q6, Q8, Q9, Q10, Q12, Q14, Q15 and acceptance of DC1 to DC5. Changed the resolution order to template, published before, stage, and removed the stage "Draft" (Active plus linked jumps to Webflow Draft). Added payload v2 (template and product separated) with a legacy adapter, `custom_` field conversion, `web_badge` with Discontinued, the staging safety design, the opaque progress dialog, the Product Data tab, and the deferral of n8n node rewrites. Corrected the earlier misreading of Discontinued in the Transform node and flagged the `default:` public risk. Added newly verified findings: hardcoded production n8n URLs in ERPNext, wrong Webflow credentials in the staging workflow, the Internal Only readiness conflict, and the `active` guard. Added Appendices C (what can fail), D (spec calculations) and E (`custom_` inventory).
- 0.5 (2026-10-31): recorded Q7, Q13, Q16, Q17 and Q18. Replaced the effective-badge design (DC7) with the owner's design: manual `web_badge`, no `Discontinued` option, new read-only `is_discontinued` checkbox, Webflow override logic deferred (R1). `web_badge` replaces `product_badge` entirely. `custom_dimensions_image_2` deleted; the product keeps `dimensions_image`. Approved the Q18 a, b, d, e names. Added D43 to D47, tests 36 to 39, and open question Q19. Unblocked Phases 1b, 2 and 5 from the answered questions.
- 0.6 (2026-10-31): recorded Q19 as D48: `is_discontinued` is computed from the resolver's effective state. Resolver output gains `is_discontinued` (replacing `badge`). Test 33b added. No open questions remain.
- 0.7 (2026-11-04): Phases 0 to 4 consolidated from the phase notes; staging-to-main checklist merged into section 10. Decisions D49 to D61 kept their numbers; owner decisions the notes left unnumbered were recorded as D62 to D83. Superseded plan text is marked, not removed. Added Q20 to Q23, 8.2 (pending and cleanup), Phase 10 (cleanup) and 10.8 (staging setup). The separate phase notes were removed (git history keeps them).
