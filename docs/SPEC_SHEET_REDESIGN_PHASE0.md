# Spec Sheet Redesign: Phase 0 Report (2026-10-31)

Plan: `erpnext_spec_sheet_redesign_plan.md` v0.6, Phase 0 (quick fixes Z1 to Z4, spikes S1 to S8).
Scope: the `staging` branch and the staging n8n workflow `NW0NxiyqKyeVrkOJ` only. Production
workflow `dvCvIpVLwzjgwccF` was read, not changed.

Base: `staging` at `d0f760f`. It is the pinned commit `1d8950f` plus one merge that already pointed
`trigger_sync_v2` (only) at the `staging-product-sync-v2` URL. That hardcoded URL is removed by Z1.

## Quick fixes

### Z1: n8n URLs and secret from site config (done, app code)

- New module `api/n8n_config.py`. No n8n URL is hardcoded anywhere in the app any more.
- `trigger_sync_v2` and `trigger_publish_v2` read `n8n_sync_webhook_url`. `request_spec_sheet` reads
  `n8n_spec_webhook_url`. A missing or non-HTTPS value stops the call with a clear message. There is
  deliberately no default, so a site without config can never fall back to production n8n.
- The triggers check the URL and secret **before** any publish job is requested, so a misconfigured
  site fails with no side effects.
- `enqueue_n8n_webhook` now sends the shared-secret header (plan 2.8 item 9). It reads the secret
  from site config when the worker runs, so the secret never travels through the job queue.
- Secret: `n8n_sync_secret`, falling back to the existing key `ERP-Sync-Secret-2026` so production
  keeps working until its config is renamed. Header name: `n8n_sync_secret_header`, default
  `ERP-Sync-Secret-2026` (the header production has always used).
- Verified finding: the **production** W2 webhook also requires Header Auth ("ERP Sync Secret"), and
  `enqueue_n8n_webhook` sent no header before this change, so production syncs dispatched through it
  would be rejected by n8n.

**Staging site config needed before testing** (names only, values from the owner):

| Key | Staging value |
|---|---|
| `n8n_spec_webhook_url` | `https://illumenatelighting.app.n8n.cloud/webhook/staging-generate-spec-sheet` |
| `n8n_sync_webhook_url` | `https://illumenatelighting.app.n8n.cloud/webhook/staging-product-sync-v2` |
| `n8n_sync_secret` | the value of the n8n credential "STAGING Sync Secret" |
| `n8n_sync_secret_header` | `STAGING-Sync-Secret` |
| `webflow_environment` | `staging` |

**Promotion note:** production must get `n8n_spec_webhook_url` and `n8n_sync_webhook_url` (and
ideally `n8n_sync_secret`) before this code reaches `main`, or the spec and sync buttons stop with
"not configured". That is the intended fail-closed behavior.

Tests: `tests/portal_unit/test_n8n_config.py` (runs without a bench) and the updated webhook tests in
`api/test_deploy_regressions.py` (bench), which now assert the header and the configured URL.

### Z2: staging Webflow credentials (done, n8n)

Published as staging version `c7764155-3e7f-46f2-8b30-e7c0b8245384`. Pre-change backup of the
workflow JSON was taken before editing (previous active version `a9edd1df-6523-40a7-b422-95f77d92abe9`
is also in the n8n version history).

| Node | Before | After |
|---|---|---|
| `(ilL) Webflow: Create Product`, `(ilL) Webflow: Update Product` | Header Auth "ERP Sync Secret" | Header Auth "Webflow ilLumenate" |
| `(206) Webflow: Create Product`, `(206) Webflow: Update Product` | Header Auth "ERP Sync Secret" (+ `Bearer null` on Create) | Header Auth "Webflow 206"; `Bearer null` header removed |
| `Publish Webflow Item (Update)` (shared) | no credential, `Bearer null` | split into `(ilL)` and `(206) Publish Webflow Item (Update)` behind `Brand: Publish (Update)` |
| `Publish Webflow Item (New)` (shared) | "Webflow 206 Prod" + `Bearer null` | split into `(ilL)` and `(206) Publish Webflow Item (New)` behind `Brand: Publish (New)` |

These are the same per-brand credentials the production draft uses on its create and update nodes.
No Webflow node uses the ERP credential any more.

**ERP secret exposure:** the staging workflow has **no recorded executions**, so as far as n8n's
execution history shows, no staging run reached the four nodes that would have sent the "ERP Sync
Secret" header to Webflow. Execution data can be pruned, so rotating that secret remains the safe
choice (it is already on the promotion checklist).

Two existing W2 bugs fixed on the way (both would have broken staging tests):

- `Should Publish? (New)` compared the booleans `isDraft` and `isArchived` to the string `"false"`
  under strict type validation. It now uses the same boolean check as `Should Publish? (Update)`.
- Both `Respond to ilL-Publication-Job` callbacks sent `webflow_item_id: $json.id`, which after a
  publish is the publish response (no `id`). A newly created item would then have been acknowledged
  with no item ID and failed. They now read the ID from the create or update response.

### Z3: fail-closed `default:` (done, n8n)

Both Transform nodes: the `default:` branch now sets `hidden-from-public = true`. Any unknown, empty or
renamed status is hidden. Checked with a local harness against the exact node code: Draft, Webflow
Draft, Publish, Discontinued, Archived, empty, a typo and a missing key.

### Z4: staging safety guards (done: n8n and app; one-time reset run on staging 2026-10-31)

n8n (staging workflow only):

- Transform nodes: every item is `hidden-from-public = true` whatever the status; name prefixed
  `[staging] `, slug and `erp-sync-id` prefixed `staging-`. The ERP product slug sent back in the
  callback is unchanged, so `mark_webflow_synced` still finds the product.
- Before every PATCH: `(ilL|206) Staging Guard: Get Item` reads the item from Webflow and
  `Staging Guard: Check Item` aborts unless its name starts with `[staging]` (test matrix 31).
- Before every publish: `Staging Guard: Before Publish (Update|New)` aborts unless the item's name
  starts with `[staging]` and `hidden-from-public` is on.
- W2 has no unpublish step yet (that is Phase 9). When it is added, it needs the same guard.

App:

- `api/staging_webflow_reset.py::clear_production_webflow_ids` (plan 4.11 item 2). It refuses to
  run unless `webflow_environment` is `staging`, requires System Manager, and is a dry run unless
  `dry_run=False`. It clears product item IDs (`ilL-Product-Publication` remote ID, staged/live
  hashes and dates, the product `sync_targets` rows and the legacy `webflow_item_id`) and marks open
  publish jobs SUPERSEDED. Categories keep their IDs (plan 4.11 item 5). It returns a report of every
  ID it cleared.
- Staging banner on the `ilL-Webflow-Product` form (plan 4.11 item 6), driven by
  `webflow_environment`. Template forms get it with the Phase 6 UI work.

**To run on staging (after deploying this branch and setting `webflow_environment = staging`):**

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.api.staging_webflow_reset.clear_production_webflow_ids
```

Review the dry-run report (it is also the S6 answer), then:

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.api.staging_webflow_reset.clear_production_webflow_ids --kwargs "{'dry_run': False}"
```

**Result (2026-10-31, run by the owner on staging):** the dry run found production Webflow item
IDs on 112 products (product field and brand sync row) and on 4 publication records (`kit-ra01`,
`kit-ra02`, `kit-az01`, `lil-sw-led`), and no open publish jobs. That answers S6: yes, staging carried
production item IDs. The reset was then applied, and a second dry run reported 0 in every category.
The owner kept the first dry-run report as the record of the cleared IDs. Staging syncs now create
new hidden `[staging]` items; the n8n guards still block any item that is not marked `[staging]`.

## Spikes

The cloud environment that ran this work cannot reach `stagingillumenate.v.frappe.cloud`, the
Webflow API, or `developers.webflow.com` (network policy). Spikes that need them are marked
**blocked** with the exact commands to run.

| Spike | Status | Result / decision |
|---|---|---|
| S1 `/files/` interception | Blocked (no access to staging) | Run Appendix B of the plan. Build `/spec-sheets/` either way. |
| S2 `/spec-sheets/<name>.pdf` route | Blocked | Needs a deployed prototype and `curl -i`. Folded into Phase 4. |
| S3 Webflow unpublish and archive | Done (docs) | See below. |
| S4 readiness and guards | Done (partly) | See below. Readiness checks confirmed; the `request()` guards and the Internal Only rule were not exercised. |
| S5 Custom Fields on `ilL-*` | Done (staging) | See below. Raises a promotion blocker and owner questions for Phase 1b. |
| S6 production item IDs on staging | Done | Yes: 112 products and 4 publications carried production IDs. Cleared on staging (see Z4). |
| S7 freeze overlay | Done (Frappe v16 source) | See below. |
| S8 Webflow `product-badge` field | Blocked (no Webflow access) | Owner reads it in the Webflow Designer (collection settings) or via `GET /v2/collections/{id}`. Information only. |

### S3: Webflow Data API v2

- **Unpublish one item:** `DELETE https://api.webflow.com/v2/collections/{collection_id}/items/{item_id}/live`.
  It removes the item from the live site and sets `isDraft = true` on the staged item. Scope `CMS:write`.
  Optional `cmsLocaleId`; without it only the primary locale is unpublished.
- **Unpublish in bulk:** `DELETE https://api.webflow.com/v2/collections/{collection_id}/items/live`, up to 100 items.
- **Archive:** `PATCH https://api.webflow.com/v2/collections/{collection_id}/items/{item_id}` with
  `{"isArchived": true}` (the staged-item update the workflow already uses). This part is from prior
  knowledge of the API, not re-read from the docs in this session; confirm when building the Phase 9 branch.
- Decision for Phase 9: the unpublish branch calls `DELETE .../items/{id}/live` first, then the
  archive PATCH when `archive = true`, then `mark_webflow_synced`, each behind the staging guard.

Sources: [Unpublish Single Live Item](https://developers.webflow.com/data/reference/cms/collection-items/live-items/delete-item-live),
[Unpublish Live Items](https://developers.webflow.com/data/reference/cms/collection-items/live-items/delete-items-live.md).

### S4: readiness on staging (run by the owner, 2026-10-31, brand `illumenate`)

| Product | Ready | Issues |
|---|---|---|
| `kit-ra01`, `kit-ra02`, `kit-ra03`, `kit-az01` | yes | none |
| `led-hd-sw` | no | see below |

`led-hd-sw` issues, traced to the code:

- "Dependency graph exceeds preflight bounds" (`product_readiness.dependency_manifest`): the walk of
  linked records passed 400 records or depth 8 (Appendix C item 21).
- "Source field is absent from the installed schema" (`product_readiness`, spec submittal check): a
  row in the template's submittal mapping names a source field that does not exist on its source
  doctype (Appendix C item 15).
- "Enter a finite positive number" twice (`authoring_contract.record_issues`): two numeric engineering
  values on linked spec records are empty, zero or invalid (Appendix C item 22). For an LED tape spec
  the checked fields are `watts_per_foot`, `voltage_drop_max_run_length_ft` and, when the tape is not
  free-cutting, `cut_increment_mm`.
- The console warning "Xref table not zero-indexed" comes from the PDF library reading the submittal
  PDF. It is not a readiness issue.

Decision: Appendix C matches the running code for the readiness checks. The kits are ready, so kits
are the right first staging sync test. `led-hd-sw` needs data fixes before it can sync; that is
catalog work, not part of this plan. The Internal Only readiness rule and the `request()` guards
(Appendix C items 1 to 5 and 8) were not exercised by this sample. They are covered when Phase 5
changes them.

### S5: Custom Fields on staging (run by the owner, 2026-10-31)

**Fields without the `custom_` prefix** (the `webflow_item_id`, `webflow_sync_*` and
`webflow_sync_targets*` group on the `ilL-Attribute-*` doctypes, and `ill_impact_task`,
`ill_next_action_by`, `ill_observed_build_hash`, `ill_review_state` on `ilL-Document-Request`) are
created by the app's own patches (`add_webflow_sync_fields_to_attributes`,
`migrate_attribute_sync_fields_to_brand_table`, `b2b_conversations`). They deploy with the code, so
they are not drift and are out of scope for D35.

**`custom_` fields on `ilL-*` doctypes (in scope for Phase 1b):**

| Doctype | Field | Type | Notes |
|---|---|---|---|
| ilL-Webflow-Product | `custom_webflow_status` | Select: Draft, Webflow Draft, **Published**, Discontinued, Archived | The option is "Published", not "Publish". See the finding below. |
| ilL-Webflow-Product | `custom_web_badge` | Select: **None**, New, On Sale, Quick Ship | `product_badge` has blank, New, On Sale, Quick Ship, **Hide**. They differ. |
| ilL-Webflow-Product | `custom_web_product_category` | **Data** | The plan expects a Link. |
| ilL-Webflow-Product | `custom_web_series` | **Data** | The plan expects a Link to `ilL-Attribute-Series`. |
| ilL-Webflow-Product | `custom_spec_custom` | Table (`ilL-Child-Webflow-Spec-Custom`) | Exists on staging, so the template mirror runs there. Production not yet checked. |
| ilL-Webflow-Product | `custom_compatible_power_supplies` | Table (`ilL-Child-Comp-Power`) | |
| ilL-Webflow-Product | `custom_dimensions_image_2` | Attach Image, "Dimensions Image (Dark)" | Deleted per D46 after its values are copied. |
| ilL-Webflow-Product | `custom_template_status` | Data | |
| ilL-Webflow-Product | `custom_min_operating_temp_c_copy` | Int | Odd name; owner to decide. |
| ilL-Webflow-Product | `custom_column_break_lgzvl` | Column Break | Its options hold a local Mac file path (a UL badge SVG). Layout only, no data. |
| ilL-Tape-Neon-Template | `custom_documents` | Table (`ilL-Child-Webflow-Document`) | Exists on the tape/neon template **only**, not on the other five. |
| ilL-Attribute-Certification | `custom_badge_image_dark`, `custom_206_badge_image_dark`, `custom_206_badge_image_light` | Attach Image | No `custom_badge_image_light`. |
| ilL-Child-Webflow-Certification-Link | `custom_badge_images` | JSON | |
| ilL-Child-Webflow-Kit-Component | `custom_webflow_title` (Data), `custom_webflow_description` (Long Text) | | |
| ilL-Child-Tape-Neon-Allowed-Option | `custom_value_label` | Data | |

That is the 15 names from Appendix E plus `custom_column_break_lgzvl`. 65 more `custom_` fields
exist on doctypes the app does not own; per plan 4.9 they are listed for the owner, not converted.

**Finding (promotion blocker, fixed in staging n8n):** the stored status option is "Published", but
both Transform nodes, in production as well as staging, only match "Publish". Published products
have therefore been falling into `default:`, which made them public by accident. With the Z3
fail-closed default, promoting the Transform nodes unchanged would have hidden every Published
product. Staging version `3ce70f5b-c475-4427-acc2-6981cc8fc86c` adds a `"Published"` case next to
`"Publish"`. Production must get the same case in the same publish as Z3.

**Questions for the owner before Phase 1b** (recommendations first):

1. `webflow_status` option name: keep **"Published"** (matches the stored data, no data change) and
   read the plan's "Publish" as that option. Recommended.
2. `web_badge` options: use blank, New, On Sale, Quick Ship, Hide (the `product_badge` set, as plan
   4.8 says), and migrate the value "None" to blank. Recommended. Confirm "Hide" is wanted.
3. `web_product_category` and `web_series` are free text today. Make them Links (category to
   `ilL-Webflow-Category`, series to `ilL-Attribute-Series`); the migration lists any value that
   matches no record and stops for the owner. Recommended.
4. Certification badge names (Appendix E said ask): `badge_image_dark`, `badge_image_206_dark`,
   `badge_image_206_light` (the brand number moved off the front so the names are valid).
5. `custom_min_operating_temp_c_copy`: delete if it holds no data, otherwise tell me what it is for.
6. `custom_column_break_lgzvl`: delete (layout only). Recommended.
7. The 65 `custom_` fields on doctypes the app does not own: leave as site Custom Fields
   (plan 4.9). Their names are needed only if you want them reviewed.

**Owner answers (2026-10-31).** New decision IDs continue the plan's log.

| ID | Decision |
|---|---|
| D49 | `webflow_status` keeps the option **"Published"**. Wherever the plan says stage "Publish", read "Published". |
| D50 | `web_badge` options: blank, New, On Sale, Quick Ship. **No "Hide"** (and no "None"). Migration: "None" becomes blank. A `product_badge` value of "Hide" becomes blank too, and the migration report lists those products. |
| D51 | Category and series on the product simply mirror the template's existing `product_category` and `series` fields. No new `web_product_category` or `web_series` fields on the template. On the product, the existing standard `product_category` and `series` Links (which the export and the publication pipeline already read) become read-only mirrors for templated products, and the duplicates `custom_web_product_category` and `custom_web_series` are **deleted, not renamed**. Supersedes the category and series parts of D34 and D47. |
| D52 | Certification badge fields: `badge_image_dark`, `badge_image_206_dark`, `badge_image_206_light`. |
| D53 | Delete `custom_min_operating_temp_c_copy` and `custom_column_break_lgzvl`. |
| D54 | The Tape/Neon template gets a real category Link (proposed name `webflow_category`, Link to `ilL-Webflow-Category`), so its products' `product_category` mirrors from the template like the other five. The existing Select `product_category` on that template stays: it is the tape family that readiness and the configurators use. |
| D55 | Products whose current `product_category` or `series` differs from the template's are listed by the migration and it stops for owner review before anything is changed. |
| Q20 (open) | Rename the `custom_` fields on doctypes the app does not own. Owner prefers the prefix `web_`. A separate step after this plan. Prefix choice pending (see below). |

Notes on D51 from the code:

- Five templates have `product_category` as a Link to `ilL-Webflow-Category`. The **Tape/Neon template's
  `product_category` is a Select** (LED Tape, COB Tape, LED Neon): it is the tape family, which
  readiness compares with the product's `product_type` (`product_readiness.py`, "Template family does
  not match product"). It is not a category record, so it cannot fill the product's category Link.
- Mirroring onto `product_category` can change the Webflow category of any product whose current value
  differs from its template's. The Phase 1 migration lists those products first and stops for review.

**Custom fields on doctypes the app does not own (staging export, 2026-10-31).** The query used
`fieldname like 'custom_%'`, where `_` is a one-character wildcard, so it also matched
`User Invitation.customer`, which is not a `custom_` field. That leaves 64:

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

"Referenced 0" only covers this repo. Fields used by n8n workflows that are not exported here, by
Webflow forms, print formats, reports or server scripts on the site would also need updating.

**Data checks to run on staging** (`bench --site stagingillumenate.v.frappe.cloud console`), read-only:

```python
P = "tabilL-Webflow-Product"
for f in ("custom_webflow_status", "custom_web_badge", "product_badge"):
    print(f, frappe.db.sql(f"select `{f}`, count(*) from `{P}` group by `{f}`"))
print("temp copy set:", frappe.db.sql(f"select count(*) from `{P}` where ifnull(custom_min_operating_temp_c_copy, 0) != 0"))
for f, dt in (("custom_web_product_category", "ilL-Webflow-Category"), ("custom_web_series", "ilL-Attribute-Series")):
    vals = frappe.db.sql_list(f"select distinct `{f}` from `{P}` where ifnull(`{f}`, '') != ''")
    print(f, len(vals), "distinct; no matching record:", [v for v in vals if not frappe.db.exists(dt, v)])
```

### S7: why the "Syncing to Webflow" box is see-through

Confirmed from Frappe `version-16` source (`frappe/public/js/frappe/dom.js`, `frappe/public/scss/desk/global.scss`):

- `frappe.dom.freeze(msg)` renders the message **inside** `<div id="freeze" class="modal-backdrop fade">`.
- `#freeze.in { opacity: 0.8; }`. Opacity on a parent applies to all its children, so the card can
  never be more than 80% opaque, whatever its own background.
- The app's override `.freeze { background-color: rgba(0,0,0,0.75) … }` targets a class that does
  not exist on that element (it has an id `freeze`), so it changes nothing.

Decision: as planned in 4.13, the Phase 3 helper must render the backdrop and the card as siblings,
not use `frappe.dom.freeze`. Optional live check on staging: open the product, click Sync, and inspect
`#freeze` in DevTools.

### Commands for the blocked spikes (run on the staging site)

S4 (readiness and guards on sample products), in `bench --site stagingillumenate.v.frappe.cloud console`:

```python
from illumenate_lighting.illumenate_lighting.api.publication import inspect
for name in frappe.get_all("ilL-Webflow-Product", pluck="name", limit=5):
    r = inspect(name, "illumenate")
    print(name, r["readiness"]["ready"], [i["message"] for i in r["readiness"]["issues"]])
```

Note `inspect()` needs catalog-reader access (run as Administrator) and is not read-only: it creates
or updates the `ilL-Product-Publication` row and its `current_hash`. Leave the console without
`frappe.db.commit()` if you want nothing kept.

S5 (Custom Fields on the app's own doctypes):

```python
rows = frappe.get_all("Custom Field", filters={"dt": ["like", "ilL-%"]},
    fields=["dt", "fieldname", "fieldtype", "options", "label"], order_by="dt, fieldname")
for r in rows: print(r.dt, r.fieldname, r.fieldtype, r.options or "", r.label or "", sep=" | ")
other = frappe.get_all("Custom Field", filters={"dt": ["not like", "ilL-%"], "fieldname": ["like", "custom_%"]},
    fields=["dt", "fieldname"])
print(len(other), "custom_ fields on doctypes the app does not own")
```

Run the same on production (read-only) to compare.

## What is next

Phase 0 is complete except for S1 and S2 (folded into Phase 4) and S8 (information only). Phase 1b
waits on the owner's answers to the S5 questions and the data checks above. The plan says to report before Phase 1. Phase 1a does not depend on those spikes,
but Phase 1b depends on S5's Custom Field export, and Phase 4 on S1 and S2.
