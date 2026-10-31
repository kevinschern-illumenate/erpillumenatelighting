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

### Z4: staging safety guards (done: n8n and app; one-time reset not yet run)

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

Until it has run, the n8n guards are what protects live items: any sync of a product carrying a
production item ID now fails at `Staging Guard: Check Item` instead of modifying the live item.

## Spikes

The cloud environment that ran this work cannot reach `stagingillumenate.v.frappe.cloud`, the
Webflow API, or `developers.webflow.com` (network policy). Spikes that need them are marked
**blocked** with the exact commands to run.

| Spike | Status | Result / decision |
|---|---|---|
| S1 `/files/` interception | Blocked (no access to staging) | Run Appendix B of the plan. Build `/spec-sheets/` either way. |
| S2 `/spec-sheets/<name>.pdf` route | Blocked | Needs a deployed prototype and `curl -i`. Folded into Phase 4. |
| S3 Webflow unpublish and archive | Done (docs) | See below. |
| S4 readiness and guards | Blocked | Commands below. |
| S5 Custom Fields on `ilL-*` | Blocked | Commands below. |
| S6 production item IDs on staging | Blocked; tool ready | The dry run of `clear_production_webflow_ids` answers it. |
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

Phase 0 is complete except for the blocked spikes (S1, S2, S4, S5, S6, S8) and running the one-time
reset on staging. The plan says to report before Phase 1. Phase 1a does not depend on those spikes,
but Phase 1b depends on S5's Custom Field export, and Phase 4 on S1 and S2.
