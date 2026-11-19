# Webflow Gallery sync (ERPNext → n8n → Webflow)

Living document. Update it in the same change as the code it describes.

| | |
| --- | --- |
| Status | **Code complete through Task 8 and the final whole-branch review (fixes applied 2026-11-18).** Staging run pending: nothing is deployed, migrated or imported yet. |
| Owner | Rei (design), Claude (build) |
| Doctype | `ilL-Webflow-Gallery` |
| Webflow collection | `Galleries` (renamed from `Projects` by Rei; the collection ID is unchanged on staging2 and differs per site, see section 9) |
| First target | Webflow **staging2** site (`6aeb4d313e25a078e9393924`), then the main site (`695c1f9a18a639365b6a31a7`) |
| Last updated | 2026-11-18 |

## 1. Intent

The Galleries section of the ilLumenate website (landing page with filters, and the gallery detail template)
is finished in Webflow staging2 and approved. It was built under the name "Projects"; Rei is renaming it to
Galleries everywhere, including the Webflow collection. Its content is currently typed directly into the Webflow CMS.

We want **ERPNext to be the single source of truth** for that content. Staff create and edit galleries in
ERPNext only. n8n publishes them to Webflow. Webflow becomes a read-only mirror: anything edited there
directly is overwritten by the next sync.

The existing ERPNext doctype `ilL Project` is something else (a dealer-portal project with a customer, fixture schedule and privacy
flag). It is not reused.

## 2. Goals, non-goals, anti-goals

**Goals**
- One ERP record per gallery, covering every field the Webflow Galleries collection has today (section 5).
- Publish through the same *approve, stage, publish live* discipline products use, so a gallery cannot go
  public without passing readiness checks and a person's approval.
- Safe to retry: no duplicate Webflow items after a crash, timeout or rate limit.
- Prove the whole path on staging2 before touching the main site.
- Import the 5 real galleries that exist in Webflow today (the placeholder "Boutique Hotel Lounge" is left
  out), so nothing is retyped and no Webflow item is duplicated.

**Non-goals (for now)**
- Two-way sync. ERP to Webflow only.
- Editing galleries in Webflow after cutover.
- Multi-locale galleries. Primary locale only, same as products.
- Restructuring the Webflow CMS fields. See section 11 (future work).
- Changing the Webflow page designs.

**Anti-goals (a failure even if it technically works)**
- Any change that can break live product publishing. The product publication code is on the live path.
- A gallery going live without a readiness check and an explicit approval.
- Duplicate items in Webflow.
- Private ERP files or secrets reaching Webflow or the n8n execution history.

## 3. Decisions made

| Decision | Made by |
| --- | --- |
| Doctype is named `ilL-Webflow-Gallery` | Rei |
| ERPNext is the only place galleries are edited; Webflow is a mirror | Rei |
| New, separate n8n workflow following the product-sync pattern (not an extension of `dvCvIpVLwzjgwccF`) | Rei, approach A |
| Use the publication process (readiness checks, approval, staged vs live, job queue) | Rei |
| Two-step flow in ERP: `Approve and Stage`, then `Publish Live` | Rei |
| Scope is galleries only; products stay in `ilL-Webflow-Product` | Rei (agreed), Claude proposed |
| Test on ERP staging and Webflow staging2 first, main site after | Rei |
| "Project" is renamed "Gallery" everywhere (ERP and Webflow collection) | Rei |
| No separate hero image field: the first row of the gallery images is the hero image | Rei |
| Series lives on the products-used table (a `series` column), not as its own field; series required; integrator required; people and companies kept in one `credits` table (section 5.1) | Rei |
| Webflow collection URL slug is now `/gallery` | Rei |

## 4. Approaches considered

1. **A. New n8n workflow following the product-sync pattern. Chosen.** ERP queues jobs, n8n claims and
   executes them. The brand table decides which Webflow site a job targets, so promotion is a configuration
   change plus a second workflow deployment.
2. **B. Extend the existing workflow `dvCvIpVLwzjgwccF`.** Rejected: about 60 nodes, also generates spec
   sheets, and sits on the live product path.
3. **C. Scheduled poll only.** Rejected as the main design (edits appear late, no approval step). The
   workflow still has a schedule trigger as a safety net that drains the queue.

### Reuse of the publication code (Claude's call, please check)

The publication doctypes carry a `listing_doctype` / `listing_name` link, which suggested galleries could
plug in. Reading `api/publication.py` (624 lines) shows it is hard-wired to products: it locks
`ilL-Webflow-Product`, builds payloads from `get_webflow_products`, uses template and product status rules,
and keys state on a product. Generalising it would touch the live product path.

**Call:** build a thin, parallel gallery path (`ilL-Gallery-Publication`, `ilL-Gallery-Publish-Job`,
`api/gallery_publication.py`) that copies the *behaviour* (approved/staged/live hashes, immutable jobs, claim
with lease, acknowledge, retry with backoff, reconcile) and imports the shared helpers (`fingerprint`,
`canonical_json`, brand resolution, contract helpers) without editing product code. Revisit merging them
later, once galleries are proven.

## 5. Data model

### 5.1 `ilL-Webflow-Gallery`

Naming: by `slug` (the ERP name is also the Webflow `erp-sync-id`). Renaming is disabled (`allow_rename` 0): a
rename would skip the slug lock and leave the publication record keyed on the old name, and the worker would
then create a second Webflow item. Attachments from the gallery form default to public
(`make_attachments_public`). Mapping to the existing Webflow fields:

| ERP field | Type | Webflow field (slug) | Notes |
| --- | --- | --- | --- |
| `gallery_title` | Data, required | `name` | |
| `slug` | Data, required, unique | `slug` | lowercase letters, numbers, hyphens |
| `is_active` | Check | n/a | Inactive means retire/archive in Webflow |
| `featured` | Check | `featured` | Badge, sorts first |
| `gallery_images` | Table: `ilL-Child-Webflow-Gallery-Image` | `gallery` **and** `featured-image` | Existing child doctype. **The first row is always the hero image** (card thumbnail and detail hero): the projection also writes it to `featured-image`, and the form says so under the table. Order is the table's row order (drag to reorder); `display_order` is ignored. `alt_text` is carried to Webflow. At least one row is required |
| `seo_description` | Small Text | `short-description` | About 160 characters, used for SEO. (Renamed in ERP; the Webflow field keeps its slug unless Rei renames it, then tell me and the mapping changes) |
| `about` | Small Text | `about` | Information about the space, the intended lighting and the mood. The field description in ERP says so |
| `case_study` | Text Editor | `case-study` | Optional; empty hides the section |
| `gallery_type` | Select | `project-type` | One value from the fixed list (16 options). (Renamed in ERP; Webflow slug unchanged unless Rei renames it) |
| `applications` | Table MultiSelect to `ilL-Gallery-Application` | `applications` | Projection outputs comma-separated names |
| `services_provided` | Table MultiSelect to `ilL-Design-Service` | `services-provided` | Projection outputs comma-separated names |
| `products_used` | Table: `ilL-Child-Gallery-Product` with `product` (Link `ilL-Webflow-Product`, optional), `series` (Link `ilL-Attribute-Series`, **required on every row**) and `note` | `products-used` (multi-reference), `product-notes` (rich text) and `series-used` (text) | One row per product or series used. The projection resolves each product to its Webflow item ID for the target brand, builds one `Name: note` paragraph per row that has a product and a note, and writes `series-used` as the distinct series names across all rows (comma-separated, in row order). A row with a series and no product (for example "Custom") only contributes to series-used |
| `quote`, `quote_attribution` | Small Text | `quote`, `quote-attribution` | Optional |
| `location` | Data | `location` | City, state |
| `completion_date` | Date | `completion-date` | Month and year matter; used for sorting |
| `credits` | Table: `ilL-Child-Gallery-Credit` (columns `credit_type`, `credit_name`, `website`) | the six name and website pairs below | One row per type, each type at most once. Types: Integrator, Architect, Designer, Contractor, Owner, Photographer. An **Integrator row is required** |
| `videos` | Small Text | `videos` | One or more links (YouTube, Vimeo, Loom, .mp4) |
| `custom_items` | Table: `item_name`, `detail`, optional `image` | `custom-items` | Projection builds rich text, one paragraph per item, image directly under its paragraph. A set image follows the same public-file and image-type rules as gallery images |
| `target_brands` | Table: `ilL-Child-Webflow-Brand-Target` | n/a | Which brands receive this gallery |
| `sync_targets` | Table: `ilL-Child-Webflow-Sync-State` | n/a | Written only by the import (section 9a): the existing Webflow item ID per brand, status `Pending`; nothing updates it afterwards. The publication record (`ilL-Gallery-Publication`, section 5.2) is the real holder of the remote item ID and sync state; it takes the imported ID when it is first created |

The projection (ERP fields to Webflow payload) lives in one place, so changing how Webflow stores the
people and company fields (section 11) only changes the mapping, not the doctype.

How the `credits` rows map to the existing Webflow fields (name, website):

| `credit_type` | Webflow name field | Webflow website field |
| --- | --- | --- |
| Integrator | `client-integrator` | `client-website` |
| Architect | `architect` | `architect-website` |
| Designer | `designer` | `designer-website` |
| Contractor | `contractor` | `contractor-website` |
| Owner | `owner` | `owner-website` |
| Photographer | `photo-credit` | `photographer-website` |

The child doctype is deliberately not named after the existing dealer-portal `ilL Project Party`.

Allowed values for gallery type, applications and services come from the help text of the existing Webflow
collection (16 gallery types, 20 applications, 8 services). Staff pick them from lists rather than typing:
two small list doctypes (`ilL-Gallery-Application`, seeded with those values, and `ilL-Design-Service`) back
the multi-selects. `ilL-Design-Service` is named generically because Rei sees another use for it later.
The series column links to the existing `ilL-Attribute-Series` doctype (one record per series, with
`series_name` and `code`). A **"Custom" series record is added** (code to be chosen, for example `CUSTOM`) for
galleries with custom items. Rei confirmed it is fine if the existing attribute sync publishes a "Custom"
item in the Webflow Series collection; **Rei will hide that option manually in the All Products section
afterwards.** This is a manual step on each Webflow site (see the promotion steps in section 9). Where the
chosen product already has a series, the form may default the column from it (builder's call). The
allowed values are mirrored by the Webflow filter script's expectations.

### 5.2 Publication records (modelled on the product ones)

- `ilL-Gallery-Publication`: one per (gallery, brand). Holds `current_hash`, `approved_hash`, `staged_hash`,
  `live_hash`, `remote_item_id`, `state` (`NEEDS_REVIEW`, `READY`, `QUEUED`, `STAGED`, `LIVE`, `FAILED`,
  `RETIRED`), `readiness_json`, approver and timestamps.
- `ilL-Gallery-Publish-Job`: immutable job per request. Operation `STAGE`, `PUBLISH` or `RETIRE`; payload and
  hash; state `QUEUED`, `RUNNING`, `COMPLETE`, `FAILED`, `SUPERSEDED`; lease token and expiry; attempts and
  next attempt time; remote item ID; last error (no response bodies, no secrets).

### 5.3 Brand configuration

- Add `Galleries` to the `collection_kind` options of `ilL-Webflow-Brand-Collection`.
- On ERP staging, use the **existing `illumenate` brand record**, which already points at Webflow staging2
  (site ID `6aeb4d313e25a078e9393924`, Products collection `6aeb4d313e25a078e9393a2a`): add a Galleries row
  (collection ID `6afb3d27742d050cf6903677`) and turn sync on. Do not create a separate brand code for the
  test site: the staging product workflow (`[STAGING] Spec Gen & Webflow Sync`) routes jobs by brand code and
  only knows `illumenate` and `lighting_206`, so products cannot be published under any other code, and
  galleries need their products published first. The same code on the production ERP points at the main
  site, so `illumenate` means "this ERP's own Webflow site" in each environment. The brand record is named by
  its brand code, so its `name` equals `brand_code` (`illumenate`). It **must set
  `erpnext_base_url`** to the ERP host the images are served from (on ERP staging,
  `https://stagingillumenate.v.frappe.cloud`); without it, image URLs use the default production host and
  Webflow's image fetches fail.
- Add the main-site brand record at promotion time (site ID `695c1f9a18a639365b6a31a7`).

## 6. Publication flow

1. Staff create or edit a gallery. Any save moves every publication of the gallery to `NEEDS_REVIEW` until
   it is inspected again (opening the form, a request or a claim). If the hashes then still match (the save
   changed nothing sent to Webflow, for example a second brand target), the state returns to `STAGED` or
   `LIVE`; a change that alters the projection hash stays `NEEDS_REVIEW` and needs a new approval. `QUEUED`,
   `FAILED` and `RETIRED` are never restored this way. `Publish Live` is enabled from the hashes (approved
   and staged equal the current hash, live does not), not from the state.
2. The `Webflow publication` panel on the form (rebuilt on every refresh) shows the checks below for a
   chosen brand.
   A **status pill** on its own row at the top of the form's sidebar (above the title row) shows where the gallery
   stands for the chosen brand: *Needs staging* (never staged), *Changes not staged* (edited since it was
   staged or live), *Queued* (waiting for n8n), *Staged* (a draft in Webflow), *Live*, *Failed* (the last job
   failed) and *Retired*. It comes from the same inspect result as the panel, so it follows the panel's brand
   picker and is rebuilt on every refresh; hover for what it means.
3. `Approve and Stage` creates a `STAGE` job. n8n writes the item to Webflow as a draft/staged item.
4. `Publish Live` creates a separate `PUBLISH` job. n8n publishes the staged item.
5. Deactivating a gallery and requesting retirement creates a `RETIRE` job. n8n unpublishes and archives the
   item. The ERP record is kept.

Repeated requests. A request for a revision that already has a `QUEUED` or `RUNNING` job of the same
operation returns that job (a double click does nothing). Any other earlier job (complete, failed or
superseded) does not block it: an unchanged revision can be requested again, which creates a new job (for
example after retire and reactivation, or after an edit is undone). Each job's `request_key` stays unique.

A successful stage does not mean live. Approved, staged and live hashes are stored separately.

**What "staged" and "live" mean in Webflow.** Both happen on the same site, exactly as for products
(see `docs/B2B_PUBLICATION_RUNBOOK.md`). *Staged* is the CMS item as saved but not published; *live* is the
published copy. `STAGE` creates or updates the item without publishing it; `PUBLISH` calls the item-publish
endpoint; `RETIRE` unpublishes and archives. Drift checks compare the staged and live copies separately.
Webflow staging2 is simply the test site, with its own staged and live copies.

## 6a. Rules that follow from the flow (Claude's calls)

- **Permissions.** Reuse the product process's roles: `ilL Catalog Publisher` approves and publishes,
  `ilL Integration` is for the n8n integration user only. The author may approve their own gallery.
- **Dependency changes.** The gallery hash includes the Webflow item ID and name of each product it uses.
  The product code is not touched. Instead, the hash is recomputed when the gallery is inspected (opening
  the form), when a job is requested, and when n8n claims a job. A mismatch supersedes the job and sends the
  gallery back to `NEEDS_REVIEW`. There is no scheduled sweep: a `LIVE` gallery whose product changes is not
  flagged in the list view until someone opens it (section 11).
- **Product Webflow item IDs.** A product's item ID in a brand is resolved in this order
  (`api/gallery_products.py`, `product_item_id`, used by the publication service and the import): (1) the
  product publication record's `remote_item_id` (`ilL-Product-Publication`, scope key
  `fingerprint([product, brand])`), which is where the product publication process keeps it; (2) the
  product's sync-state row for the brand, whatever its status (every product save sets it to `Pending`);
  (3) the product's own `webflow_item_id`, for the default brand only. None of these means the product is
  not staged in the brand.
- **Slug.** Locked after the first `STAGE`, and the gallery cannot be renamed. To change a published
  gallery's slug, retire it and create a new one.
- **Import** (section 9a) is an ERP-side script, not an n8n workflow.

### Readiness checks (initial list)

Blocking:
- Title and slug present; slug valid and unique for the brand.
- At least one gallery image. The first row becomes the hero image, so it must be a public image file of a
  supported type (jpg, jpeg, png, webp, gif). File size is not checked.
- Every gallery image is a public file of a supported type; no private ERP file URLs.
- Every custom item with an image: the image is a public file of a supported type (it is written into the
  `custom-items` rich text).
- Gallery type is one allowed value; applications and services each from allowed values.
- **Products used has at least one row, and every row has a series** (required), each an active series record.
  A row with a series and no product is valid and only adds to series-used.
- **Integrator is required:** a credits row of type Integrator with a name. (Claude's call: the integrator's website is not blocking, it gives a warning if missing.)
- Every product in `products_used` is already staged in the target brand (has a Webflow item ID, resolved
  as in section 6a). Rows without a product are skipped here.
- Every website field is a valid `https` URL when filled.
- Videos are valid links from supported hosts when filled.
- Brand is active, sync enabled, targeted by this gallery, and has the Galleries collection ID set.

Warnings (shown, not blocking):
- SEO description longer than about 160 characters, or empty.
- Integrator has no website.
- No completion date (sorting).
- No `about` text (the space, intended lighting and mood).

## 7. n8n workflow

- New file `n8n_workflows/webflow_gallery_sync.json`, generated by a builder script modelled on
  `tools/build_publication_workflow.py`, with the projection logic in a checked-in library next to
  `n8n_workflows/lib/product_projection.js`.
- **One workflow deployment per brand**, as for products: credentials in n8n are bound per workflow, not
  looked up from ERP. Staging deployment uses the ERP staging integration user and the staging2 Webflow
  credential. The production deployment uses the production ones.
  **Variables are account-wide.** The workflow reads `ILL_ERP_BASE_URL` and `ILL_WEBFLOW_BRAND` from n8n
  variables, which the whole n8n account shares, and the staging product workflow does not use them. Staging
  alone can use them as they are (set `ILL_ERP_BASE_URL=https://stagingillumenate.v.frappe.cloud` and
  `ILL_WEBFLOW_BRAND=illumenate`). A production copy in the same account cannot read different values from
  the same variables, so before production the builder needs options to build in the ERP address and brand
  (section 11).
- Flow: trigger (manual, or the **Gallery Webhook** that ERP calls; no schedule, so nothing runs while there
  is no work, see 7a) → claim a job for `$vars.ILL_WEBFLOW_BRAND` at `$vars.ILL_ERP_BASE_URL` →
  match the remote item (by `erp-sync-id`, falling back to exact slug and verifying `erp-sync-id`) → create
  or update the staged item → for `PUBLISH`, publish live → acknowledge to ERP with job ID, lease token,
  hashes and the remote item ID.
- Built: `tools/build_gallery_workflow.py` writes `n8n_workflows/webflow_gallery_sync.json` (inactive,
  credentials unbound; regenerate, never hand-edit) and embeds `n8n_workflows/lib/gallery_projection.js`
  (`projectWebflowGallery(payload, {isDraft})`). The Webflow calls and error codes are the product
  worker's: list/get items, `POST`/`PATCH` the item, `POST .../items/publish`, `DELETE .../items/{id}/live`
  then `PATCH {isArchived: true}`. Codes: `transport`, the HTTP status (`429` with `retry_after`),
  `identity-conflict`, `missing-staged-item`, `publication-unverified`, `archive-unverified`,
  `projection-invalid`, `response-invalid`, and gallery-only `lookup-incomplete`.
- Matching. A known remote item ID is fetched directly; it must carry this `erp-sync-id`, or none yet with
  the same slug (an imported item; the write backfills `erp-sync-id`). Without an ID, Webflow cannot filter
  by `erp-sync-id`, so the worker reads one page of 100 items and looks for `erp-sync-id` first (this finds
  an item created before a lost acknowledgement), then the exact slug. A slug match with another or empty
  `erp-sync-id`, or two candidates, is `identity-conflict`. If the collection has more than 100 items the
  worker stops with `lookup-incomplete` (permanent) rather than risk a duplicate; add paging before then.
- `STAGE` writes the item as a draft; `PUBLISH` needs the staged item (else `missing-staged-item`), writes
  it with `isDraft: false` and publishes it, verified by `publishedItemIds`. `RETIRE` unpublishes and
  archives, never deletes; an item already absent counts as retired.
- Null-vs-omit rule (comment in `gallery_projection.js`): every text and rich-text field is always sent,
  `''` when empty, so a value cleared in ERP is cleared in Webflow; `gallery` and `products-used` are
  always arrays; `featured-image` is `{url, alt}` or null. An unfilled credit pair is never sent as empty
  strings: a credit type not in the payload sends null for both slugs (clears a removed credit), and a
  credit without a website sends null for the website. `completion-date` is an ISO date-time and is omitted
  when ERP has no date, so clearing the date in ERP leaves the old Webflow date.
- Acknowledgements carry only job, token, hashes, remote item ID, outcome, error code and `retry_after`:
  never a Webflow response body or a credential.
- Retry and error rules follow the product worker: claims last five minutes; a temporary failure (rate
  limit, timeout, connection, 5xx) is retried after 1, then 5, then 15 minutes (`next_retry` in
  `api/publication_contract.py`), and a lease that runs out is a timeout. Permanent errors, and temporary ones
  after the third retry, notify once and stay visible in ERP for correction and explicit retry.
- Images are passed to Webflow as public URLs. ERP files must therefore be public files on an HTTPS origin.
  The projection percent-encodes each URL's path (`/files/Lilium Static White_Hero.png` becomes
  `/files/Lilium%20Static%20White_Hero.png`): Webflow rejects a URL with spaces when it imports the image on
  publish ("Invalid file url"), although it accepts it in a draft.
- Multi-reference `products-used` is written with Webflow item IDs of the products in the same site.

### 7a. ERP is the trigger (no polling)

The workflow has no schedule. ERP POSTs `{"brand": ...}` to the workflow's webhook, with the shared secret
header from site config, and the workflow then claims a job as before. The nudge is sent (in the background,
after the request commits) when a job is requested, when **Retry** is pressed, when Approve is pressed again
for a job still queued, and by the minute tick for each brand with a retry that has fallen due (leases that
ran out become retries first). An execution therefore happens only when there is work.

Site config on each ERP site: `n8n_gallery_webhook_url` (the workflow's production webhook URL, https), plus the
existing `n8n_sync_secret` and `n8n_sync_secret_header` (the header name must match the n8n Header Auth
credential on the webhook node). If the URL is missing the job stays Queued and one Error Log a day says
why. If n8n is down when a job is requested it also stays Queued; approving again sends the nudge again.

## 8. Webflow changes needed

- Add a plain-text field `erp-sync-id` to the Galleries collection on each site (same as Products has).
- Rename the collection to Galleries on staging2 (done by Rei). Its URL slug is now `/gallery` (was
  `/projects`), so gallery pages are `/gallery/<slug>`. At build time, search the Designer links (navbar,
  the "More" section, the services banner) and the filter and template scripts (embeds
  `0dbe336e-e001-8dcd-ad70-ebb652eefba2` and `0a7e4ee9-2abd-c8d5-8df7-80f785c117f5`) for hard-coded
  `/projects` and update them. Field slugs are unchanged. The Webflow API collection slug is now `gallery`.
  If `/projects` URLs were ever public on the main site, add a 301 redirect to `/gallery`.
- The main site must have a Galleries collection with identical field slugs before promotion. Pasting the
  gallery elements in the Designer does **not** copy collection schema; create the collection on the main
  site first, then paste, then rebind.
- No design changes to the page templates.

## 9. Environments and promotion

| | ERP | n8n workflow | Webflow site |
| --- | --- | --- | --- |
| Test | `stagingillumenate.v.frappe.cloud` (brand `illumenate`) | gallery workflow, staging deployment | staging2 (`6aeb4d313e25a078e9393924`) |
| Production | `app.illumenate.lighting` (brand `illumenate`) | gallery workflow, production deployment | main site (`695c1f9a18a639365b6a31a7`; Galleries collection ID to be recorded) |

Promotion steps, only after staging2 is verified:
1. Merge `staging` to `main` through the normal PR flow (check what else the PR carries: `staging` is usually
   ahead of `main` by more than the gallery work), migrate the production ERP.
2. Create the Galleries collection and `erp-sync-id` on the main site (same field slugs as staging2; the schema
   can be copied through the Webflow API); paste the Designer pieces and rebind. Check links and redirects for
   `/projects`.
3. Production ERP: point the `illumenate` brand at the main site, add its Galleries collection row and set its
   Webflow Site URL; add `n8n_gallery_webhook_url` (the production webhook URL) to site config, next to the
   existing n8n secret settings; stage the real products.
4. n8n: import `n8n_workflows/webflow_gallery_sync_production.json` (inactive; built with
   `https://app.illumenate.lighting`, brand `illumenate` and webhook path `ill-gallery-sync`, see section 7),
   bind the production Header Auth credential to the webhook and the production ERP and Webflow credentials to
   the HTTP nodes, then activate it.
5. Re-run the import against production (dry run first), approve one gallery, verify on the main site, then
   the rest.
6. Manual (Rei): hide the "Custom" option in the All Products section on the site, once the Series sync has
   created it.

## 9a. Importing the existing galleries (Claude's call)

A whitelisted ERP method, `import_galleries(items, brand, commit=0)` (api/gallery_import.py; needs the
catalog publisher capability; run from the System Console or a bench command), creates one
`ilL-Webflow-Gallery` per item. ERP holds no Webflow token, so the method does not call the Webflow API:
the controller exports the Galleries collection items (JSON exactly as the Webflow v2 list-items API
returns them) and passes them in. The pure mapping is `map_webflow_item`.

- Matching: by exact slug. The existing Webflow item ID is written to the gallery's sync state and
  `erp-sync-id` is backfilled on the Webflow item at the first sync, so the first sync updates the item
  instead of duplicating it.
- Images: downloaded from the public Webflow CDN URLs in the items (no credentials) and attached in ERP as public files. The first sync re-sends them
  to Webflow, which creates new assets; the old ones are left as unused assets.
- Hero image: the existing items already list the hero image as the first gallery image, so the gallery rows
  import in order and the first row is the hero.
- People: the six name and website pairs on each item become `credits` rows (only the pairs that are filled).
- Series: the old `series-used` text is matched to `ilL-Attribute-Series` records by name; "Custom LED Tape"
  and "Custom Extrusion Kit" go to "Custom", and "Ode Wellness" (no series today) is set to "Custom" (Rei).
  Each series goes on a `products_used` row. An item with **no** `series-used` text is "Custom" (Rei):
  every product row takes "Custom", ignoring the product's own series, so `series-used` is "Custom" only
  (Ode Wellness). An item that has series text: a product row takes the product's own series (whether or
  not the text lists it); a product without a series takes "Custom" when the item lists no other series.
  A product whose series cannot be determined is left out and reported. Listed series that no product row
  took become series-only rows. Anything that can't be matched is listed in the import report.
- Galleries that still fail the readiness rules after import are imported as drafts needing review; staff
  complete them before approval.
- Products: each `products-used` Webflow item ID is mapped to an `ilL-Webflow-Product` whose item ID in the
  target brand (resolved as in section 6a) matches. A Webflow product that cannot be mapped is left out of
  `products_used` and listed in the import report, never silently dropped.
- Dry run first (`commit` defaults to 0): nothing is written to the database. The report is returned and
  also written under the site's private files. A failed image download is reported and that image row is
  skipped; an item that fails to save is rolled back and reported. Existing slugs are reported "exists,
  skipped", never overwritten. Archived items are skipped; draft items import inactive. The sync-state row
  is written with status Pending (so the first sync updates the item) and the brand is added to the
  gallery's `target_brands`.
- Run against ERP staging first, then production at promotion.

## 10. Testing

Staging, in this order: (1) one gallery end to end; (2) the 5 imported galleries compared field by field
with the existing Webflow items; (3) edit after approval (needs new approval); (4) failed update and retry;
(5) timeout after remote create (no duplicate); (6) retirement; (7) a product not staged in the brand (blocks
readiness). Automated tests: Python tests for readiness, approval and job rules (modelled on
`tests/portal_unit/test_publication.py`) and a JS test that runs the workflow's code nodes against a
simulated HTTP boundary (modelled on `tests/portal_unit/publication_workflow.test.cjs`).

## 11. Future work

- Collapse the people and company fields (integrator, architect, designer, contractor, owner, photographer and
  their websites) in Webflow into one plain-text JSON field, with a page script that parses it. Only the
  projection changes on the ERP side. Not part of this build.
- Merge the gallery and product publication code once galleries are proven.
- Let `tools/build_gallery_workflow.py` build a copy with the ERP address and brand built in (instead of n8n
  variables), so a staging and a production copy can sit side by side in one n8n account. Needed before the
  production deployment. (A version of this, with a header-token Webflow option, was built and set aside in
  PR #435 because staging alone does not need it.)
- A scheduled sweep that recomputes gallery hashes, so a `LIVE` gallery whose product changed is flagged in
  the list view without someone opening it.
- Multi-locale support.

## 12. Open questions

Resolved by Rei, 2026-11-18:
- Products are **not** yet synced from ERP staging into staging2. Prerequisite step: stage the products the
  imported galleries use (the Webflow product items referenced by the galleries, currently two distinct
  products for the five galleries to import) through the existing product publication process, before the
  gallery end-to-end test. The product readiness check is not relaxed.
- Staging n8n: a Webflow credential for staging2 already exists. (ERP-side integration user on staging to be
  confirmed when the workflow is bound.)
- "Boutique Hotel Lounge" (placeholder) is **not** imported. Five galleries are imported.

- "Ode Wellness" series is "Custom". A "Custom" item appearing in the Webflow Series collection is fine; Rei
  hides the option manually in All Products afterwards.
- The Webflow collection URL slug is `/gallery`.

- Brand code for ERP staging: the existing `illumenate` brand (decided 2026-11-18, replacing the planned
  `staging2` code; see section 5.3).

Still open: nothing.

## 13. Change log

- 2026-11-18: Document created from the design discussion. No code written.
- 2026-11-18: Rei's edits: Project renamed to Gallery everywhere (ERP and the Webflow collection, now
  "Galleries"); no separate hero field (first gallery image is the hero); `short_description` became
  `seo_description`; `about` describes the space, intended lighting and mood; list doctypes are named
  `ilL-Gallery-Application` and `ilL-Design-Service`; "Custom" series added; series and integrator are
  required; people and companies become a `credits` table; main site ID recorded.
- 2026-11-18: Rei's answers: Ode Wellness series is "Custom"; the collection URL slug is `/gallery`; a
  "Custom" series item in Webflow is fine (hidden manually later). Series moved from its own field to a
  required `series` column on the products-used table (`ilL-Child-Gallery-Product`).
- 2026-11-18: Multi-value fields decided (Rei): Table MultiSelect for applications and services (series
  later moved to the products-used table).
- 2026-11-18: Rei's answers: products need staging first, staging2 credential exists, placeholder gallery
  left out (five galleries imported, not six). Goals text updated.
- 2026-11-18: Builder review. Added what staged/live mean, permissions, dependency-change handling, slug
  locking and the import design (sections 6, 6a, 9a). Three questions left open for Rei (section 12).
- 2026-11-18: Task 1 built: `ilL-Gallery-Application`, `ilL-Design-Service`, the four child doctypes
  (`ilL-Child-Gallery-Application`, `-Service`, `-Credit`, `-Product`), `api/gallery_schema.py`, the
  `seed_gallery_lists` patch (lists plus the "Custom" series) and the `Galleries` brand collection kind.
- 2026-11-18: Task 2 built: `ilL-Webflow-Gallery` (autoname by slug, `sync_targets` read-only), the
  `ilL-Child-Gallery-Custom-Item` child doctype and `api/gallery_rules.py` (`validate_gallery`: slug format,
  slug lock after staging, slug uniqueness, one credit per type).
- 2026-11-18: Task 3 built: `api/gallery_readiness.py` (`evaluate`, `is_public_file`), the pure readiness
  checks from section 6. The returned `dependencies` carry product Webflow item IDs and series used.
- 2026-11-18: Task 4 built: `api/gallery_projection.py` (`build_payload`, `absolute_url`), the pure projection
  from section 5.1. Hero is the first image row; public paths become absolute on the brand's base URL; plain
  text in rich-text fields is HTML-escaped; applications, services and series are returned as lists.
- 2026-11-18: Task 6 built: gallery form script (`public/js/gallery_publication.js`, wired through `doctype_js`
  and `ill_webflow_gallery.js`) with a brand picker, readiness list (issues red, warnings grey), `Approve and
  Stage`, `Publish Live`, `Retire` and a failed-job `Retry`, plus a hero-image note under the images table.
- 2026-11-18: Task 7 built: `n8n_workflows/lib/gallery_projection.js`, `tools/build_gallery_workflow.py` and the
  generated `n8n_workflows/webflow_gallery_sync.json` (manual plus webhook trigger since 2026-11-19, inactive, credentials
  unbound), and `tests/portal_unit/gallery_workflow.test.cjs` (run in CI). Section 7 records the matching
  rule, the `lookup-incomplete` stop above 100 items and the null-vs-omit rule. The staging2 Galleries
  collection does not have the `erp-sync-id` field yet (section 8); add it before the first sync.
- 2026-11-18: Task 8 built: `api/gallery_import.py` (`map_webflow_item`, `import_galleries`). Per Rei's ruling the
  ERP does not call Webflow: the controller passes the exported items in (section 9a updated).
- 2026-11-18: Final whole-branch review fixes. Added the missing `ilL-Child-Gallery-Custom-Item` controller.
  A series-only `products_used` row no longer blocks readiness or breaks the hash. Product Webflow item IDs
  are resolved from the product publication record, then the sync row (any status), then the product's own
  field for the default brand (section 6a); the import uses the same order. A repeated request for an
  unchanged revision creates a new job unless one is queued or running. A save that changes nothing sent
  returns the publication to `STAGED`/`LIVE` on the next inspect, and `Publish Live` follows the hashes.
  Custom-item images must be public image files; gallery attachments default to public; galleries cannot be
  renamed. The import never writes a product row without a series, and an item with no series text stays "Custom" only. Gallery wording for `identity-conflict`,
  `lookup-incomplete` and `readiness` failures. The form panel is rebuilt on every refresh. This document:
  status, the sweep (not built; section 11), `sync_targets`, image size, the staging2 brand's
  `erpnext_base_url`, and the import's unmapped-product rule corrected.
- 2026-11-18: ERP staging uses the existing `illumenate` brand (already pointing at staging2) instead of a
  new `staging2` brand, because the staging product workflow only routes `illumenate` and `lighting_206`
  (section 5.3). n8n variables are account-wide, which matters before production (sections 7 and 11).
- 2026-11-19: First staging run: the draft was written, but Publish Live failed with "Remote image failed to
  import: Invalid file url" for a file name with spaces. Gallery image URLs are now percent-encoded
  (`gallery_projection.absolute_url`), as the product projection already did. Changing a URL changes the
  gallery's hash, so each gallery needs Approve and Stage again after this is deployed.
- 2026-11-19: Added the status pill to the top of the gallery form's sidebar (section 6, step 2), from the same
  inspect result as the publication panel.
- 2026-11-19: The gallery form has a collapsed "What the status means" section at the bottom (`status_guide`, an
  HTML field) listing the seven statuses the sidebar pill can show and what each means. Work now goes straight
  to `staging` rather than through feature branches.
- 2026-11-19: The gallery has a read-only `publication_status` field (list view column and standard filter) so
  galleries can be filtered by status. It holds the same seven labels as the sidebar pill. It is copied from the
  gallery's publication records whenever one changes, and when the gallery is saved (`sync_status`). With several
  target brands it shows the status that most needs attention: Failed, Queued, Changes not staged, Needs staging,
  Staged, Live, Retired. A patch fills it for existing galleries.
- 2026-11-19: The gallery form shows a preview of the first image row (the hero) above the Gallery Images table,
  with its size and an alt-text reminder, like the main image card on the template forms.
- 2026-11-19: The n8n gallery workflow is triggered by ERP instead of a one-minute schedule (section 7a). ERP calls
  the workflow's webhook when a job is requested or retried and when a retry falls due. New site config key
  `n8n_gallery_webhook_url`.
- 2026-11-19: Form layout changes. Publication Status sits under Gallery Title. Location and Completion Date moved
  to Identity, Videos to Images, and Quote and Quote Attribution follow the Case Study; the Details section is
  gone (field names are unchanged, so no data moves). Quote Attribution is hinted "Full Name, Company" and the
  Videos hint now says commas or new lines are accepted.
- 2026-11-19: A **View in Webflow** button sits with the Publication buttons. For a live gallery it opens
  `<brand Webflow Site URL>/gallery/<slug>` in a new tab (`/gallery` is the Galleries template page's published
  path). A gallery that is only staged has no public page, so the button says to use Publish Live first. The
  brand's Webflow Site URL must be the site the gallery was published to (for the staging2 site, its webflow.io
  address, not the production domain).
- 2026-11-19: Completion dates are sent to Webflow as midnight **Pacific Time** (07:00Z in daylight time, 08:00Z
  otherwise) instead of midnight UTC, so a site shown in Pacific Time reads the same day as ERP.
- 2026-11-19: The workflow looks a gallery up by slug (`?slug=`), not by scanning the first 100 items, so the size
  of the Galleries collection no longer matters. If Webflow ever ignored the filter on a collection over 100 items
  the job still stops as `lookup-incomplete`, never creating a duplicate. A consequence: an item whose slug was
  changed by hand in Webflow is no longer found by its `erp-sync-id` (ERP locks the slug once staged, and
  galleries are not edited in Webflow).
- 2026-11-19: A new publication request supersedes a failed job that is still waiting to retry, so an old STAGE
  retry can no longer run after a later Publish and set a live gallery back to Staged.
- 2026-11-19: `tools/build_gallery_workflow.py` takes `--erp-base-url`, `--brand`, `--webhook-path`, `--name` and
  `--out` to build the ERP address and brand in (n8n variables are not available on the plan); the production
  copy is `n8n_workflows/webflow_gallery_sync_production.json`.
- 2026-11-19: **Credits go to Webflow as one JSON field.** The main site's Galleries collection has a single
  plain-text `credits` field instead of the twelve name and website fields (Rei's design; a script on the
  Webflow page parses it). The workflow sends, in this fixed order and only for credits with a name,
  `[{"type":"Integrator","name":"Acme","website":"https://acme.example"},{"type":"Photographer","name":"P. Lens","website":null}]`
  on one line (types: Integrator, Architect, Designer, Contractor, Owner, Photographer; `website` is null when
  there is none). No credits sends `''`, not `[]`. The old per-person slugs are no longer sent, because Webflow
  rejects fields that are not in the collection: **a Galleries collection needs the `credits` field (and may drop
  the twelve old ones)**; the staging2 collection still has the old fields and needs `credits` added before the
  staging workflow is used again. ERP is unchanged (credits stay a table).
- 2026-11-19: Generated copies of the workflow with the ERP address, brand and webhook path built in are checked in
  for both environments: `webflow_gallery_sync_production.json` (webhook path `ill-gallery-sync`) and
  `webflow_gallery_sync_staging.json` (`ill-gallery-sync-staging`). The n8n workflow `m55OoaAD9LHaRYZq` was
  reworked into the production one; the staging copy can be re-imported from its file.
