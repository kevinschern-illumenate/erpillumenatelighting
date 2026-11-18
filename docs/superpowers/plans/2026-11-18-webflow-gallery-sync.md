# Webflow Gallery Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ERPNext holds galleries in a new `ilL-Webflow-Gallery` doctype, and an n8n workflow publishes them (approve, stage, publish live) to the Webflow Galleries collection, tested on staging2 first.

**Architecture:** A parallel, gallery-only copy of the product publication behaviour (`ilL-Gallery-Publication`, `ilL-Gallery-Publish-Job`, `api/gallery_publication.py`) that imports the shared pure helpers and never edits product code. Pure Python modules build the readiness result and the semantic payload; a checked-in JS library shapes that payload into Webflow field data; a builder script generates the n8n workflow (one deployment per brand).

**Tech Stack:** Frappe/ERPNext (Python, doctype JSON, desk JS), n8n workflow JSON (generated), Webflow CMS v2 API, `unittest` (stubbed-Frappe pattern from `tests/portal_unit/test_services.py`), Node `assert` tests, `ruff`.

**Spec:** `docs/WEBFLOW_GALLERY_SYNC.md` (read it first; it is also the living documentation and is updated in every task that changes behaviour).

## Global Constraints

- Doctype names: `ilL-Webflow-Gallery`, `ilL-Gallery-Publication`, `ilL-Gallery-Publish-Job`, `ilL-Gallery-Application`, `ilL-Design-Service`, `ilL-Child-Gallery-Credit`, `ilL-Child-Gallery-Product`, `ilL-Child-Gallery-Application`, `ilL-Child-Gallery-Service`, `ilL-Child-Gallery-Custom-Item`. Module `ilLumenate Lighting`. Existing `ilL Project` is never reused or modified.
- Never edit `api/publication.py`, `webflow_auto_push.py`, or the product workflow. Import shared helpers only: `fingerprint`, `canonical_json` (`api/configuration_contract.py`); `callback_disposition`, `next_retry`, `failure_reason`, `RETRY_MINUTES` (`api/publication_contract.py`); `resolve_brand`, `get_default_brand` (`api/webflow_brand.py`); `require`, `require_catalog_reader` (`portal/staff.py`); `webflow_notify.notify`.
- Retries use `next_retry` (1, 5, 15 minutes, then final failure notice). Lease is 5 minutes. Operations are `STAGE`, `PUBLISH`, `RETIRE`; job states `QUEUED RUNNING COMPLETE FAILED SUPERSEDED`; publication states `NEEDS_REVIEW READY QUEUED STAGED LIVE FAILED RETIRED`. (The spec's section 7 quotes an older 30-second figure; fix it in Task 5.)
- Gallery types (16): Residential, Hospitality, Restaurant, Healthcare, Education, Office, Hotel, Civic/Government, Retail, Architectural, Transportation, Landscape, Multi-family, Theater/Art, Lobby, Sports/Entertainment.
- Applications (20): Accent, Cove, Direct View, Grazing, Signage, Task, Undercabinet, Toekick, Recessed, Millwork, Perimeter, Vanity, Backlighting, Step Lighting, Display, Shelving, Washing, Suspended, Closet, Undercounter.
- Design services (8): Product Specification, Takeoff Drawings, Custom Installation Instructions, Detailed Installation Drawings, Photometric Calculations and Renderings, Conceptual 3D Renderings, Troubleshooting, End-User Training.
- Credit types and Webflow fields (name, website): Integrator `client-integrator`,`client-website`; Architect `architect`,`architect-website`; Designer `designer`,`designer-website`; Contractor `contractor`,`contractor-website`; Owner `owner`,`owner-website`; Photographer `photo-credit`,`photographer-website`. Each type at most once.
- Webflow field slugs kept as-is: `featured`, `featured-image`, `gallery`, `short-description` (from `seo_description`), `about`, `case-study`, `project-type` (from `gallery_type`), `applications`, `services-provided`, `products-used`, `series-used`, `product-notes`, `quote`, `quote-attribution`, `location`, `completion-date`, `videos`, `custom-items`, plus new `erp-sync-id`.
- Webflow IDs: staging2 site `6aeb4d313e25a078e9393924`; staging2 Galleries collection `6afb3d27742d050cf6903677` (URL slug `/gallery`); main site `695c1f9a18a639365b6a31a7`; staging brand code `staging2`.
- Images go to Webflow as public HTTPS URLs; a `/private/files/` path is never sent.
- Primary locale only. Lint with `ruff check .` and `ruff format .`. Commit messages end with the Claude co-author line. Work on branch `feature/webflow-gallery-sync`; never push to `main`.

## Review Focus

1. Reordering gallery images after approval changes the hero (first row) and must change the hash (back to `NEEDS_REVIEW`).
2. A private (`/private/files/...`) or relative image path must block readiness; a public relative path becomes an absolute URL on the brand's ERP base URL.
3. Plain text in product notes and custom items containing `<`, `&` or quotes must be HTML-escaped in the generated rich text.
4. n8n created the Webflow item but the acknowledgement was lost: the retry must find the item by `erp-sync-id` (then exact slug) and not create a second one; two matches stop with `identity-conflict`.
5. Slug rules: lowercase letters, numbers and hyphens only; locked after the first successful STAGE; a duplicate slug is refused.

---

### Task 1: List doctypes, child doctypes and seed data

**Files:**
- Create: `illumenate_lighting/illumenate_lighting/doctype/ill_gallery_application/`, `ill_design_service/`, `ill_child_gallery_application/`, `ill_child_gallery_service/`, `ill_child_gallery_credit/`, `ill_child_gallery_product/` (each `__init__.py` + `.json`; list doctypes also `.py`)
- Create: `illumenate_lighting/illumenate_lighting/api/gallery_schema.py`
- Create: `illumenate_lighting/patches/seed_gallery_lists.py`; register in `illumenate_lighting/patches.txt`
- Modify: `doctype/ill_webflow_brand_collection/ill_webflow_brand_collection.json` (add `Galleries` to `collection_kind` options)
- Test: `tests/portal_unit/test_gallery_schema.py`

**Interfaces:**
- Produces (`gallery_schema.py`): `GALLERY_TYPES: tuple[str, ...]`, `APPLICATIONS`, `DESIGN_SERVICES`, `CREDIT_TYPES: tuple[str, ...]`, `CREDIT_FIELDS: dict[str, tuple[str, str]]` (type to Webflow name and website slugs), `SLUG_RE`.
- Doctype fields: `ilL-Gallery-Application` and `ilL-Design-Service` are named by `application_name` / `service_name` (Data, required, unique) plus `is_active` (Check, default 1). `ilL-Child-Gallery-Application` has `application` (Link); `ilL-Child-Gallery-Service` has `service` (Link); both `istable`. `ilL-Child-Gallery-Credit`: `credit_type` (Select of `CREDIT_TYPES`, required), `credit_name` (Data, required), `website` (Data). `ilL-Child-Gallery-Product`: `product` (Link `ilL-Webflow-Product`, optional), `series` (Link `ilL-Attribute-Series`, required), `note` (Small Text).

- [ ] **Step 1: Write failing tests in `test_gallery_schema.py`**: `test_counts_match_spec` (16 gallery types, 20 applications, 8 services, 6 credit types); `test_credit_fields_map` (`CREDIT_FIELDS["Integrator"] == ("client-integrator", "client-website")`, and `["Photographer"] == ("photo-credit", "photographer-website")`); `test_slug_re` (accepts `ode-wellness`, `a1`; rejects `Ode`, `a b`, `a_b`, empty); `test_doctype_json_valid` (each new doctype JSON loads, `name` matches folder, child doctypes have `istable == 1`, `ilL-Child-Gallery-Product.series.reqd == 1`, brand collection `collection_kind` options contain `Galleries`).
- [ ] **Step 2: Run** `cd tests/portal_unit && python -B -m unittest test_gallery_schema -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Create `gallery_schema.py` and the doctype JSON files**, copying the layout of `ill_child_webflow_gallery_image.json` (editable grid for children; permissions for list doctypes: System Manager full, `ilL Catalog Publisher` read/write/create).
- [ ] **Step 4: Write `patches/seed_gallery_lists.py`** with an `execute()` function that inserts any missing `ilL-Gallery-Application` and `ilL-Design-Service` rows from the schema lists, and a `Custom` `ilL-Attribute-Series` record (`series_name="Custom"`, `code="CUSTOM"`, `is_active=1`) if absent. Idempotent. Register in `patches.txt`.
- [ ] **Step 5: Add a test** `test_seed_patch_idempotent` using the stubbed-Frappe pattern (second run inserts nothing). Run the module. Expected: PASS.
- [ ] **Step 6: Update `docs/WEBFLOW_GALLERY_SYNC.md`** (status and change log), then commit: `git add -A && git commit -m "feat(gallery): list doctypes, child doctypes, seeds"`.

### Task 2: `ilL-Webflow-Gallery` doctype and its validation

**Files:**
- Create: `doctype/ill_webflow_gallery/ill_webflow_gallery.json`, `ill_webflow_gallery.py`, `__init__.py`
- Create: `illumenate_lighting/illumenate_lighting/api/gallery_rules.py`
- Test: `tests/portal_unit/test_gallery_rules.py`

**Interfaces:**
- Consumes: Task 1 `gallery_schema`.
- Produces (`gallery_rules.py`, pure): `validate_gallery(doc: dict, *, slug_locked: bool, slug_taken: bool) -> list[str]` returning blocking error messages (empty list means valid).
- Doctype: `autoname` `field:slug`; fields exactly as spec section 5.1 (`gallery_title`, `slug`, `is_active`, `featured`, `gallery_images`, `seo_description`, `about`, `case_study`, `gallery_type`, `applications`, `services_provided`, `products_used`, `quote`, `quote_attribution`, `location`, `completion_date`, `credits`, `videos`, `custom_items`, `target_brands`, `sync_targets`). `custom_items` is a table of an `ilL-Child-Gallery-Custom-Item` child (`item_name` Data required, `detail` Small Text, `image` Attach Image). The `about` field description reads "Information about the space, the intended lighting and the mood". A description under `gallery_images` states that the first row is always the hero image. `sync_targets` and `target_brands` reuse `ilL-Child-Webflow-Sync-State` and `ilL-Child-Webflow-Brand-Target`.

- [ ] **Step 1: Write failing tests**: `test_slug_must_match_re`; `test_duplicate_credit_type_rejected` (two `Integrator` rows gives an error naming the type); `test_slug_locked_after_stage` (`slug_locked=True` and a changed slug is refused: pass the old slug as `doc["_old_slug"]`); `test_slug_taken_rejected`; `test_first_image_is_hero_note_not_a_field` (the doctype JSON has no `hero_image` field and `gallery_images` description contains "first row").
- [ ] **Step 2: Run to confirm FAIL.**
- [ ] **Step 3: Implement `validate_gallery`** and the doctype JSON. The controller's `validate()` gathers `slug_locked` (a publication for this gallery has `staged_hash` set) and `slug_taken` (another gallery with the slug), calls the pure function, and `frappe.throw`s the joined messages. `webflow_item_id` is never edited by hand: make `sync_targets` read-only on the form.
- [ ] **Step 4: Run tests. Expected: PASS.** Run `ruff check .`.
- [ ] **Step 5: Update the spec doc; commit** `feat(gallery): ilL-Webflow-Gallery doctype and validation`.

### Task 3: Readiness evaluation (pure)

**Files:**
- Create: `illumenate_lighting/illumenate_lighting/api/gallery_readiness.py`
- Test: `tests/portal_unit/test_gallery_readiness.py`

**Interfaces:**
- Consumes: Task 1 `gallery_schema`.
- Produces: `evaluate(gallery: dict, *, config: dict, product_refs: dict[str, dict], active_series: set[str]) -> dict` returning `{"ready": bool, "issues": [Issue], "warnings": [Issue], "dependencies": dict}` where `Issue = {"record": str, "field": str, "message": str}`. `config` is the `resolve_brand` dict (needs `is_active`, `sync_enabled`, `collections`, `erpnext_base_url`). `product_refs[name] = {"name": str, "webflow_item_id": str | None}` for the target brand. `is_public_file(url: str) -> bool`.

- [ ] **Step 1: Write failing tests** (one per rule, each asserting the `field` of the issue): no gallery images; first image is a `/private/files/x.jpg` path (blocking, `field == "gallery_images"`) while `/files/x.jpg` passes; `gallery_type` not in `GALLERY_TYPES`; `products_used` empty; a row without a series; a series not in `active_series`; no Integrator credit; Integrator without a name; a product with `webflow_item_id None` (`record` is the product name); website not `https`; video link not from YouTube, Vimeo, Loom or a `.mp4`; brand inactive, `sync_enabled` false, no `Galleries` collection. Warnings (not blocking, `ready` stays true): `seo_description` over 160 characters or empty; Integrator without a website; no `completion_date`; no `about`. Plus `test_fully_valid_gallery_is_ready`.
- [ ] **Step 2: Run to confirm FAIL.**
- [ ] **Step 3: Implement `evaluate`** (`ready` is true only when `issues` is empty; `dependencies` lists the product names and IDs and series used, so the hash changes when a product's Webflow ID changes).
- [ ] **Step 4: Run tests. Expected: PASS.** Commit `feat(gallery): readiness checks`.

### Task 4: Payload projection (pure)

**Files:**
- Create: `illumenate_lighting/illumenate_lighting/api/gallery_projection.py`
- Test: `tests/portal_unit/test_gallery_projection.py`

**Interfaces:**
- Consumes: Task 1 `gallery_schema`.
- Produces: `build_payload(gallery: dict, *, base_url: str, product_refs: dict[str, dict]) -> dict` with keys `schema_version` (1), `erp_sync_id`, `slug`, `name`, `featured`, `hero_image` (`{"url","alt"}`), `gallery_images` (list of the same, in row order, hero included first), `seo_description`, `about`, `case_study_html`, `gallery_type`, `applications` (names), `services_provided` (names), `series_used` (distinct names across `products_used` rows, row order), `product_item_ids`, `product_notes_html`, `quote`, `quote_attribution`, `location`, `completion_date` (`YYYY-MM-DD` or null), `credits` (`{type: {"name","website"}}`), `videos` (list), `custom_items_html`. Also `absolute_url(path: str, base_url: str) -> str`.

- [ ] **Step 1: Write failing tests**: `test_first_row_is_hero` (and reversing the rows changes `hero_image` and the whole payload); `test_relative_public_path_becomes_absolute`; `test_series_distinct_in_row_order` (rows `[Custom, COB, Custom]` gives `["Custom","COB"]`); `test_series_only_row_adds_series_not_notes`; `test_product_notes_one_paragraph_per_row_with_note` (`<p>Rainier [SF]: White finish</p>`); `test_notes_escape_html` (note `a<b & "c"` is escaped); `test_custom_items_image_under_its_paragraph`; `test_videos_split_on_commas_and_newlines`; `test_credits_only_filled_types`; `test_payload_is_deterministic` (two calls, same `fingerprint`).
- [ ] **Step 2: Run to confirm FAIL.**
- [ ] **Step 3: Implement `build_payload`** with no Frappe imports; escape with `html.escape`.
- [ ] **Step 4: Run tests. Expected: PASS.** Commit `feat(gallery): payload projection`.

### Task 5: Publication doctypes, API and scheduler wiring

**Files:**
- Create: `doctype/ill_gallery_publication/`, `doctype/ill_gallery_publish_job/` (json, py, `__init__.py`; read-only permissions as in `ill_product_publication.json`)
- Create: `illumenate_lighting/illumenate_lighting/api/gallery_publication.py`
- Modify: `illumenate_lighting/hooks.py` (doc_events invalidation for `ilL-Webflow-Gallery`; one cron entry for `gallery_publication.tick`; `doctype_js` for Task 6), `docs/WEBFLOW_GALLERY_SYNC.md` section 7 (retry figures)
- Test: `tests/portal_unit/test_gallery_publication.py` (stubbed Frappe, same style as `test_publication.py`)

**Interfaces:**
- Consumes: Tasks 3 and 4 (`evaluate`, `build_payload`); shared helpers listed in Global Constraints.
- Produces (all `@frappe.whitelist(methods=["POST"])`, dotted path `illumenate_lighting.illumenate_lighting.api.gallery_publication.<name>`): `inspect(gallery, brand) -> dict`; `request(gallery, brand, operation, expected_hash) -> dict`; `claim(brand, limit=1) -> {"jobs": [...]}`; `acknowledge(job, token, revision_hash, payload_hash, remote_item_id=None, outcome="success", error_code=None, retry_after=None) -> dict`; `retry(job) -> dict`; plain functions `expire_leases(now=None) -> list[str]`, `retry_brands(now=None) -> list[str]`, `invalidate_gallery(doc, method=None) -> None`, `tick() -> None`. Claimed job dict: `job, token, operation, revision_hash, payload_hash, remote_item_id, payload`.
- Doctype fields mirror `ilL-Product-Publication` / `ilL-Publish-Job` with `gallery` (Link `ilL-Webflow-Gallery`) in place of `product`; publication `scope_key` is `fingerprint([gallery, brand])`.

- [ ] **Step 1: Write failing tests**: `test_request_requires_current_hash`; `test_request_blocks_when_not_ready`; `test_publish_requires_staged_approved_revision`; `test_request_is_idempotent` (same key gives the same job); `test_claim_supersedes_job_when_hash_changed` (hero reorder or product ID change between request and claim); `test_claim_sets_lease_and_attempts`; `test_acknowledge_stage_sets_staged_hash`; `test_acknowledge_publish_sets_live_hash`; `test_retire_clears_hashes`; `test_stale_callback_does_not_clear_new_revision`; `test_remote_identity_conflict_refused`; `test_temporary_failure_schedules_retry` (429 gives a `next_attempt_on`; 400 gives none); `test_expire_leases_marks_timeout`; `test_invalidate_sets_needs_review`; `test_slug_locks_after_stage` (publication with `staged_hash` makes Task 2's `slug_locked` true).
- [ ] **Step 2: Run to confirm FAIL.**
- [ ] **Step 3: Implement the doctypes and `gallery_publication.py`** by following `api/publication.py` function by function (`_locked`, `_refresh`, `request`, `_job_locked`, `claim`, `acknowledge`, `_fail`, `_notify_if_final`, `retry`, `expire_leases`, `retry_brands`). Differences: the gallery is the locked record; `_refresh` loads the gallery, resolves `product_refs` from each product's sync state for the brand, gets `evaluate` and `build_payload`, and hashes `{payload, dependencies}` with `fingerprint`; `active` means `is_active` and the brand is targeted (`target_brands`, or the default brand when empty). `request` and `claim` require the same capabilities as products (`require("catalog")`, `require("integration")`). Failure and success notices call `webflow_notify.notify` with the gallery doctype. No `webflow_approvals` calls.
- [ ] **Step 4: Wire `hooks.py`**: `doc_events` for `ilL-Webflow-Gallery` `on_update` calls `invalidate_gallery`; add a cron `* * * * *` entry for `gallery_publication.tick`, which runs `expire_leases` as the same service user the product tick uses (read `webflow_auto_push.tick` and `portal/service_users.py`; do not modify them).
- [ ] **Step 5: Run the module and the whole folder**: `cd tests/portal_unit && python -B -m unittest discover -s . -v`. Expected: PASS, no product test changes.
- [ ] **Step 6: Fix the retry wording in section 7 of the spec doc, commit** `feat(gallery): publication jobs and API`.

### Task 6: Gallery form (readiness panel and buttons)

**Files:**
- Create: `illumenate_lighting/public/js/gallery_publication.js`, `doctype/ill_webflow_gallery/ill_webflow_gallery.js`
- Modify: `illumenate_lighting/hooks.py` (`doctype_js` entry)
- Test: `tests/portal_ui/gallery_publication.test.cjs` (pattern: `tests/portal_ui/desk_scripts.test.cjs`)

**Interfaces:**
- Consumes: Task 5 whitelisted methods.
- Produces: on the form, a brand picker, a readiness list (issues in red, warnings in grey), and three buttons that call `inspect`, then `request` with `operation` `STAGE`, `PUBLISH` or `RETIRE` and `expected_hash`: `Approve and Stage`, `Publish Live`, `Retire`. `Publish Live` is disabled until the publication state is `STAGED` and its approved hash equals the current hash. `Retire` is disabled while `is_active` is on. Add a failed-job `Retry` button.

- [ ] **Step 1: Write failing UI test**: buttons present only for saved docs; `Publish Live` disabled until staged; clicking `Approve and Stage` calls `request` with the `expected_hash` returned by `inspect`; issues render with their record and message.
- [ ] **Step 2: Run** `node tests/portal_ui/gallery_publication.test.cjs`. Expected: FAIL.
- [ ] **Step 3: Implement the scripts** following `public/js/product_publication.js`.
- [ ] **Step 4: Run the test. Expected: PASS.** Commit `feat(gallery): form readiness panel and publish buttons`.

### Task 7: n8n projection library, workflow builder and workflow

**Files:**
- Create: `n8n_workflows/lib/gallery_projection.js`, `tools/build_gallery_workflow.py`, `n8n_workflows/webflow_gallery_sync.json` (generated)
- Modify: `.github/workflows/b2b-contracts.yml` (add `node tests/portal_unit/gallery_workflow.test.cjs`)
- Test: `tests/portal_unit/gallery_workflow.test.cjs` (pattern: `publication_workflow.test.cjs`)

**Interfaces:**
- Consumes: Task 5 claimed job shape; Task 4 payload keys.
- Produces (`gallery_projection.js`, CommonJS): `projectWebflowGallery(payload: object, options: {isDraft: boolean}) -> {isArchived: false, isDraft: boolean, fieldData: object}` using exactly the Webflow slugs in Global Constraints, `erp-sync-id` from `payload.erp_sync_id`, `featured-image` from `payload.hero_image`, `gallery` from `payload.gallery_images`, `series-used` and `applications` and `services-provided` joined with `, `, `videos` joined with `, `, credits mapped by the six name/website pairs (omit unfilled pairs), `completion-date` as an ISO string.
- Workflow: manual trigger plus a schedule trigger (every minute); `claim` for brand `$vars.ILL_WEBFLOW_BRAND` at `$vars.ILL_ERP_BASE_URL`; match the remote item by `erp-sync-id`, falling back to exact slug and verifying `erp-sync-id`; `STAGE` creates or updates the staged item, `PUBLISH` calls item publish, `RETIRE` unpublishes and archives; then `acknowledge`. Use the same Webflow calls and error mapping as `build_publication_workflow.py` (codes `transport`, `429`, `identity-conflict`, `missing-staged-item`, `publication-unverified`, `archive-unverified`).

- [ ] **Step 1: Write failing JS tests** against the generated workflow with a transport double: `test_projection_maps_every_field_slug`; `test_stage_creates_item_once`; `test_lost_ack_after_create_does_not_duplicate` (second run finds the item by `erp-sync-id`); `test_slug_fallback_verifies_erp_sync_id`; `test_two_matches_is_identity_conflict`; `test_publish_requires_staged_item`; `test_retire_unpublishes_and_archives`; `test_rate_limit_acknowledges_429_for_retry`; `test_unfilled_credit_omitted`.
- [ ] **Step 2: Run** `node tests/portal_unit/gallery_workflow.test.cjs`. Expected: FAIL.
- [ ] **Step 3: Implement the library and builder**; run `python -B tools/build_gallery_workflow.py` to write the workflow JSON. The workflow stays inactive, credentials unbound.
- [ ] **Step 4: Run the test. Expected: PASS.** Run the existing product workflow test to confirm it still passes: `node tests/portal_unit/publication_workflow.test.cjs`.
- [ ] **Step 5: Update the spec doc (section 7), commit** `feat(gallery): n8n workflow and projection library`.

### Task 8: Import of the existing galleries

**Files:**
- Create: `illumenate_lighting/illumenate_lighting/api/gallery_import.py`
- Test: `tests/portal_unit/test_gallery_import.py`

**Interfaces:**
- Consumes: Task 1 schema, Task 2 doctype.
- Produces (pure): `map_webflow_item(item: dict, *, series_by_name: dict[str, str], product_by_webflow_id: dict[str, str], skip_slugs: set[str]) -> tuple[dict | None, list[str]]` returning the gallery dict (or `None` when skipped) and report lines. Whitelisted: `import_galleries(brand, commit=0) -> dict` (dry run unless `commit` is 1; returns the report, and writes the same to a file under the site's private files).

- [ ] **Step 1: Write failing tests** using the fixture item shapes from the spec (Ode Wellness, Holodeck Wall, Lowlander): `test_skips_boutique_hotel_lounge` (default `skip_slugs={"boutique-hotel-lounge"}`); `test_ode_series_is_custom`; `test_custom_led_tape_and_extrusion_kit_map_to_custom`; `test_credit_pairs_become_rows_only_when_filled`; `test_gallery_rows_keep_order_hero_first`; `test_unmapped_product_reported_not_dropped`; `test_existing_webflow_id_goes_to_sync_state`; `test_dry_run_writes_nothing`.
- [ ] **Step 2: Run to confirm FAIL.**
- [ ] **Step 3: Implement.** Read items from the Webflow Galleries collection with the brand's credentials (config), download each image and attach it as a public ERP file, never overwrite an existing gallery with the same slug, and write the report.
- [ ] **Step 4: Run tests. Expected: PASS.** Commit `feat(gallery): import of existing Webflow galleries`.

### Task 9: Staging2 setup and end-to-end test (operational)

**Files:** `docs/WEBFLOW_GALLERY_SYNC.md` (status, test results, change log). No new code unless a defect is found; fix defects with a failing test first.

- [ ] **Step 1: Webflow field.** With the Webflow MCP (session `ses_3MCFzlJm7Bzl6hmaul6amvswPBU`) create plain-text field `erp-sync-id` on collection `6afb3d27742d050cf6903677`. Verify with `get_collection_details`. Search the Designer embeds `0dbe336e-e001-8dcd-ad70-ebb652eefba2` and `0a7e4ee9-2abd-c8d5-8df7-80f785c117f5` and the navbar and CTA links for `/projects` and fix. Ask Rei before removing any element Rei built.
- [ ] **Step 2: Ship to ERP staging.** Open a PR to `staging`; after merge, Frappe Cloud deploys to `stagingillumenate.v.frappe.cloud`; run migrate. Expected: patches run, new doctypes appear, "Custom" series exists.
- [ ] **Step 3: Brand record.** Create the `staging2` `ilL-Webflow-Brand` (site ID, `Galleries` collection ID, products collection, ERP base URL, sync enabled) on ERP staging. Confirm the integration System User exists and has `ilL Integration`.
- [ ] **Step 4: Stage the products first.** Stage the two products the five galleries use (Webflow product IDs `6aeb4d313e25a078e9393da4` and `6afcb6975a2c9531e2d0280f`) to `staging2` through the existing product publication process. Verify each shows a Webflow item ID in its sync state for `staging2`.
- [ ] **Step 5: Import.** Run `import_galleries(brand="staging2")` dry run, read the report with Rei, then `commit=1`. Expected: five galleries; Ode Wellness series is Custom.
- [ ] **Step 6: n8n.** Import `webflow_gallery_sync.json` inactive into `illumenatelighting.app.n8n.cloud`; set `ILL_ERP_BASE_URL` and `ILL_WEBFLOW_BRAND=staging2`; bind the staging ERP credential and the existing staging2 Webflow credential to every HTTP node.
- [ ] **Step 7: Run the test sequence** from spec section 10, recording results in the doc: one gallery stage then publish live and compare with the existing item; the five galleries field by field; edit after approval needs new approval; failed update and retry; timeout after create (no duplicate); retirement; product not staged blocks readiness. Publish the staging2 site only after Rei confirms.
- [ ] **Step 8: Commit** the doc updates.

### Task 10: Promotion to the main site (operational; start only when Rei says staging2 is verified)

**Files:** `docs/WEBFLOW_GALLERY_SYNC.md`.

- [ ] **Step 1: PR `staging` to `main`** through the normal flow; migrate production ERP (`app.illumenate.lighting`).
- [ ] **Step 2: Main Webflow site `695c1f9a18a639365b6a31a7`:** create the Galleries collection with identical field slugs plus `erp-sync-id`; paste the Designer pieces; rebind CMS; Rei hides the "Custom" option in All Products.
- [ ] **Step 3: Production brand record, products staged, n8n production deployment** (inactive), production credentials bound, then import against production (dry run first).
- [ ] **Step 4: Approve one gallery, run manually, verify on the main site, then enable the schedule.** Record the result in the doc.
