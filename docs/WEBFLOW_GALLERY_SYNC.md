# Webflow Gallery sync (ERPNext → n8n → Webflow)

Living document. Update it in the same change as the code it describes.

| | |
| --- | --- |
| Status | **Design approved. Build in progress:** list doctypes, child doctypes and seed patch done (Task 1); `ilL-Webflow-Gallery` doctype and validation done (Task 2). |
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

Naming: by `slug` (the ERP name is also the Webflow `erp-sync-id`). Mapping to the existing Webflow fields:

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
| `custom_items` | Table: `item_name`, `detail`, optional `image` | `custom-items` | Projection builds rich text, one paragraph per item, image directly under its paragraph |
| `target_brands` | Table: `ilL-Child-Webflow-Brand-Target` | n/a | Which brands receive this gallery |
| `sync_targets` | Table: `ilL-Child-Webflow-Sync-State` | `erp-sync-id` plus item ID | Per-brand Webflow item ID and status |

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
- Add an ERP-staging brand record for Webflow staging2 (brand code `staging2`, site ID
  `6aeb4d313e25a078e9393924`, Galleries collection ID `6afb3d27742d050cf6903677`, sync enabled).
- Add the main-site brand record at promotion time (site ID `695c1f9a18a639365b6a31a7`).

## 6. Publication flow

1. Staff create or edit a gallery. Any change that alters the projection hash moves its publication back to
   `NEEDS_REVIEW`.
2. `Readiness and Publication` on the form shows the checks below for a chosen brand.
3. `Approve and Stage` creates a `STAGE` job. n8n writes the item to Webflow as a draft/staged item.
4. `Publish Live` creates a separate `PUBLISH` job. n8n publishes the staged item.
5. Deactivating a gallery and requesting retirement creates a `RETIRE` job. n8n unpublishes and archives the
   item. The ERP record is kept.

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
  The product code is not touched. Instead, the hash is recomputed whenever the gallery is inspected or a
  job is requested, and again when n8n claims a job. A mismatch supersedes the job and sends the gallery
  back to `NEEDS_REVIEW`. A scheduled sweep recomputes hashes so a changed product surfaces in the list view.
- **Slug.** Locked after the first `STAGE`. To change a published gallery's slug, retire it and create a
  new one.
- **Import** (section 9a) is an ERP-side script, not an n8n workflow.

### Readiness checks (initial list)

Blocking:
- Title and slug present; slug valid and unique for the brand.
- At least one gallery image. The first row becomes the hero image, so it must be a public image file of a supported type and size.
- Every gallery image is a public file; no private ERP file URLs.
- Gallery type is one allowed value; applications and services each from allowed values.
- **Products used has at least one row, and every row has a series** (required), each an active series record.
- **Integrator is required:** a credits row of type Integrator with a name. (Claude's call: the integrator's website is not blocking, it gives a warning if missing.)
- Every product in `products_used` is already staged in the target brand (has a Webflow item ID).
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
- Flow: trigger (schedule, manual, optional ERP webhook nudge) → claim a job → match the remote item (by
  `erp-sync-id`, falling back to exact slug and verifying `erp-sync-id`) → create or update the staged item →
  for `PUBLISH`, publish live → acknowledge to ERP with job ID, lease token and hashes.
- Retry and error rules follow the product worker: claims last five minutes, exponential backoff from 30
  seconds capped at one hour and eight attempts, permanent errors stay visible in ERP for correction and
  explicit retry.
- Images are passed to Webflow as public URLs. ERP files must therefore be public files on an HTTPS origin.
- Multi-reference `products-used` is written with Webflow item IDs of the products in the same site.

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
| Test | `stagingillumenate.v.frappe.cloud` | gallery workflow, staging deployment | staging2 (`6aeb4d313e25a078e9393924`) |
| Production | `app.illumenate.lighting` | gallery workflow, production deployment | main site (`695c1f9a18a639365b6a31a7`; Galleries collection ID to be recorded) |

Promotion steps, only after staging2 is verified:
1. Merge to `main` through the normal PR flow, migrate the production ERP.
2. Create the Galleries collection and `erp-sync-id` on the main site; paste the Designer pieces.
3. Create the main-site brand record; import workflow as inactive; bind production credentials.
4. Re-run the import against production, approve one gallery, execute manually, verify, then enable the schedule.
5. Manual (Rei): hide the "Custom" option in the All Products section on the site, once the Series sync has
   created it.

## 9a. Importing the existing galleries (Claude's call)

A whitelisted ERP method (run from the System Console or a bench command) reads the Galleries collection
from the Webflow API and creates one `ilL-Webflow-Gallery` per item.

- Matching: by exact slug. The existing Webflow item ID is written to the gallery's sync state and
  `erp-sync-id` is backfilled on the Webflow item at the first sync, so the first sync updates the item
  instead of duplicating it.
- Images: downloaded from the Webflow CDN and attached in ERP as public files. The first sync re-sends them
  to Webflow, which creates new assets; the old ones are left as unused assets.
- Hero image: the existing items already list the hero image as the first gallery image, so the gallery rows
  import in order and the first row is the hero.
- People: the six name and website pairs on each item become `credits` rows (only the pairs that are filled).
- Series: the old `series-used` text is matched to `ilL-Attribute-Series` records by name; "Custom LED Tape"
  and "Custom Extrusion Kit" go to "Custom", and "Ode Wellness" (no series today) is set to "Custom" (Rei).
  Each series goes on a `products_used` row. A product row takes the series of the same name when the
  product's own series matches one of the listed values; remaining series become series-only rows. Anything
  that can't be matched is listed in the import report.
- Galleries that still fail the readiness rules after import are imported as drafts needing review; staff
  complete them before approval.
- Products: each `products-used` Webflow item ID is mapped to an `ilL-Webflow-Product` through its sync state
  for the target brand. An item whose product cannot be mapped is imported with that row left empty and
  listed in the import report, never silently dropped.
- Dry run first, report to a file, nothing written without `--commit`.
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

Still open:
- Brand code for the staging2 brand record: `staging2` (Claude's call).

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
