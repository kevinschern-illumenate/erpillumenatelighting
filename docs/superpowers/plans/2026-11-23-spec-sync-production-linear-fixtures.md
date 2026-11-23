# Spec Generator & Webflow Sync to Production (Linear Fixtures first): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the staging spec generator and Webflow product sync on production ERPNext (`app.illumenate.lighting`), with a new production n8n workflow writing to the production Webflow site (`illumenate.lighting`). Limit it to Linear Fixtures (`ilL-Fixture-Template`) and the `illumenate` brand until each later product type is turned on.

**Architecture:** Nothing new is invented. The code on `main` and `staging` is already the same (`origin/staging` is 1 gallery commit ahead), and production ERP already has the redesign schema (`product_status` has "Active + Live", the Webflow Product fields are renamed). The work is in four parts:
1. A **sync scope gate** in site config, so production only generates and syncs fixture templates for `illumenate`.
2. **Doctype filters** on the bulk data tools.
3. A **checked-in builder** that turns the exported staging n8n workflow into the production workflow, following the gallery sync pattern (`tools/build_gallery_workflow.py`, `webflow_gallery_sync_production.json`).
4. An **operator runbook** (Part B) that applies §10 of the redesign plan to production, pilot first.

**Tech Stack:** Frappe/ERPNext v16 app (Python, `unittest` service tests in `tests/portal_unit` via `load_service`), n8n Cloud workflow JSON, Node assert tests (`*.test.cjs`), Webflow CMS v2.

**Spec:** `docs/erpnext_spec_sheet_redesign_plan.md`:
- §10 "Moving from staging to main (promotion checklist)", written by the owner and Kevin; this plan carries it out.
- §9.1, staging acceptance: passed 2026-11-08 to 11-12, on kit KIT-RA02, **not on a fixture**.
- §8.2, open items.

The pattern to copy: `docs/WEBFLOW_GALLERY_SYNC.md` §9 and §11.

## Decisions (owner, 2026-11-23)

| # | Decision |
|---|---|
| P1 | **New production n8n workflow** `[PROD] Spec Gen & Webflow Sync`, with new webhook paths. The old `Spec Gen & Webflow Sync` (`dvCvIpVLwzjgwccF`) is backed up and left unpublished. It has 0 executions retained, and its product path throws, because `API_TOKENS` is never defined in `Set Brand Config`. Cutover and rollback are a change of site config URLs. |
| P2 | **`illumenate` brand only** in this phase. The 206 branch is built without staging guards, but its routes end in "brand not enabled" until 206 is promoted. |
| P3 | **Code allowlist** in site config (`webflow_sync_scope`), checked by Generate Spec, bulk regeneration, Sync/Publish and the automatic push. |
| P4 | **Builder plus test.** The staging workflow is exported into the repo. `tools/build_spec_sync_workflow.py` produces the production JSON, and CI proves no staging value survives. |
| P5 | Production ERP host is **`https://app.illumenate.lighting`**, for both API calls and the absolute image and PDF URLs written to Webflow. |
| P6 | **Pilot, then batch.** 1–3 pilot fixtures first; `webflow_auto_push` stays **off** until the batch is verified. |
| P7 | **Claude builds, the owner or Kevin operate.** Claude writes the code, the workflow JSON and the runbook, and may run read-only dry runs on production. A person approves and runs every production write: site config, migrate, `apply=True`, the n8n publish, Webflow Designer changes. |

## What was found (2026-11-23 review)

**Repo**
- Your teammate's prep is merged on `main`. There is no unmerged prep branch, and the stale pre-2026-10-30 branches have no common history with `main`. The prep is:
  - the checklist, `erpnext_spec_sheet_redesign_plan.md` §10
  - `webflow_promotion.py`: `backfill_published_on`, `auto_push_preview`, `check_integration_users`, `repair_sync_item_ids`
  - `api/n8n_config.py`: webhook URLs and the secret come only from site config
- The live spec/sync workflow is **not** in the repo. Only four Code-node snippets are, under `n8n_workflows/lib/`, and two of them hard-code `stagingillumenate.v.frappe.cloud`. `n8n_workflows/webflow_product_sync.json` is a different (generic) workflow.
- `regenerate_spec_sheets` already takes `doctypes`. `refresh_all_templates`, `promote_live_templates` and `link_consistency_report` act on every template type.

**n8n**
- Staging `NW0NxiyqKyeVrkOJ` has 55 nodes; its saved version is the same as its published version.
- Its webhooks are `staging-generate-spec-sheet` and `staging-product-sync-v2`, with the header credential `STAGING Sync Secret`.
- It already fetches the spec HTML from the **production** site, `https://illumenate.lighting/spec-sheet-templates/linear-fixtures`. That page returns 200 and carries the expected ids (`#delivered-lumens`, `#dimension-item`, `#generated-date`, …).
- **Staging bug:** `Stop and Error` refers to `$('Extract Error Message')`, a node that exists only in the old production workflow. Any ERP error on the spec path fails a second time with an expression error.
- Staging's last run (14927, 11-20) gave a 404: the PATCH used a stale item ID for `ps-univ` on the staging site.
- These production credentials already exist:

  | Credential | Type | ID |
  |---|---|---|
  | `Webflow Marketing API` | erpNextApi | `q5FbtRYh73x4yYeZ` |
  | `ERP Sync Secret` | httpHeaderAuth | `7yYX8sFrFSmjcy3n` |
  | `Webflow ilLumenate` | httpHeaderAuth, main site | `ERCkeAfdcLoATXDa` |
  | `Webflow ilLumenate Prod` | webflowApi | `etAbMh1PwKehI2qE` |
  | `Webflow 206` | — | `GxQCB7sINpN4D3B4` |

- Main-site Products collection: `696fc3c5c42c86528e97f413`.
- Unrelated but failing: `ERPNext → Webflow Product-Attribute Reference Sync` (`mpLuNTtjTvRc5uPtD_h9n`) has failed 29 of 29 runs. The error is `Field not described in schema: environment-ratings-filter` on the main Products collection. This is not part of this plan (see "Out of scope").

**Production ERP** (read only)
- 292 `ilL-Fixture-Template`: 156 Active, 132 Draft, 4 Internal Only. **None is Active + Live yet.**
- 71 `ilL-Webflow-Product` of type Fixture Template:
  - 66 are `linear-fixtures` and 5 are `landscape`.
  - 59 already have a Webflow item ID; all show `sync_status` Pending.
  - The last sync was 2026-10-30.
- Only 36 fixture templates link back to a product, so the link consistency run will matter.
- No template has a stable spec link yet.
- Brand `illumenate`:
  - Webflow site `695c1f9a18a639365b6a31a7`, site URL `https://www.illumenate.lighting`
  - `erpnext_base_url` **empty**: it falls back to `DEFAULT_ERPNEXT_BASE_URL`, which is the `v.frappe.cloud` host and goes against P5.

**Webflow:** production Products lacks only `web-badge`. Every stored fixture item ID exists on production. See "Webflow schema diff" below.

## Global Constraints

- Site config key `webflow_sync_scope`: a JSON object, or a JSON string of one (the Frappe Cloud editor stores strings, see `73a8b29`). Shape: `{"doctypes": [...], "brands": [...]}`.
  - A missing key, or a missing member, means no limit on that member. This keeps staging behaving as it does today.
  - Production value for this phase: `{"doctypes": ["ilL-Fixture-Template"], "brands": ["illumenate"]}`.
- Refusal text (exact):
  - `"{doctype} is not enabled for spec generation and Webflow sync on this site."`
  - `"Brand {brand} is not enabled for Webflow sync on this site."`
- Production ERP origin: `https://app.illumenate.lighting`. Staging origin: `https://stagingillumenate.v.frappe.cloud`.
- Production webhook paths: `ill-generate-spec-sheet` and `ill-product-sync`. They must not reuse `generate-spec-sheet-v2` or `product-sync-v2`, which belong to the old workflow kept as backup.
- Production workflow name: `[PROD] Spec Gen & Webflow Sync`. Imported with `active: false`, `settings.saveDataSuccessExecution: "none"` and `settings.saveManualExecutions: false`. n8n stores webhook headers, including the secret, in execution data (§10.6).
- Never copy staging Webflow item IDs to production. Never run `staging_webflow_reset` or `staging_webflow_remap` on production (§10.3).
- Every production data tool runs dry first. `apply=True` only after the owner has read the dry-run output.
- Lint with `ruff check .` and `ruff format .`. Tabs for indentation in Python, as the codebase does.

## Review Focus

1. **Automatic pushes on non-fixture products.** Once production has the new workflow URL, saving any other product (kit, tape, driver) must not reach n8n, even with `webflow_auto_push` on. Tested in Task 1 (`test_auto_push_refuses_out_of_scope_product`).
2. **206 target brand on a fixture.** A fixture product targeting both brands must sync `illumenate` and report 206 as not enabled, not fail the whole push. Tested in Task 1 (`test_stage_brands_skips_out_of_scope_brand`).
3. **`webflow_sync_scope` stored as a JSON string, or malformed.** A string must parse. A malformed value must refuse everything rather than allow everything (fail closed). Tested in Task 1 (`test_scope_parses_string_and_fails_closed`).
4. **A staging value left in the production workflow.** Covers the host in Code-node strings, a staging credential ID, a staging webhook path, the staging site ID `6aeb4d313e25a078e9393924` and the staging Products collection `6aeb4d313e25a078e9393a2a`. Tested in Task 4 (`test_production_has_no_staging_values`).
5. **A removed guard node leaving a dangling connection.** Products would be created but never published. Tested in Task 4 (`test_guard_removal_keeps_publish_path`).

---

# Part A: Code (repo, branch → `staging` → `main`)

Work on `claude/sharp-dijkstra-kmg183`. Open a PR to `staging` first, so staging runs the gate with the scope unset (no behaviour change) and the builder output can be checked there. Then promote to `main` the way the gallery work went (`promote/*`).

### Task 1: Sync scope gate

**Files:**
- Modify: `illumenate_lighting/illumenate_lighting/api/n8n_config.py`: add the key, parser and checks; document them in the module docstring.
- Modify: `illumenate_lighting/illumenate_lighting/spec_sheet_job.py`:
  - `generate_spec_sheet` (≈line 46): check the doctype before the readiness check, then the resolved brand.
  - `plan_regeneration` (≈line 229): skip out-of-scope rows with reason `"not enabled on this site"`.
- Modify: `illumenate_lighting/illumenate_lighting/api/webflow_export_v2.py`:
  - `stage_brands` (≈line 2756): refuse an out-of-scope template doctype. Return `{"brand", "issues": [<brand refusal>]}` for an out-of-scope brand instead of requesting a job.
  - `trigger_publish_v2` (≈line 2816): the same checks before any job is requested.
- Modify: `illumenate_lighting/illumenate_lighting/webflow_auto_push.py`: in `process` (≈line 318), an out-of-scope product or brand counts as `targeted=False` when calling `decide`. `decide` then returns its existing `DROP`: the row is deleted, no push and no notification.
- Test: `tests/portal_unit/test_n8n_config.py`, `tests/portal_unit/test_spec_sheet_job.py`, `tests/portal_unit/test_webflow_sync.py`, `tests/portal_unit/test_webflow_auto_push.py`.

**Interfaces:**
- Produces, in `n8n_config`:
  - `SCOPE_KEY = "webflow_sync_scope"`
  - `sync_scope() -> dict`: returns `{"doctypes": set|None, "brands": set|None}`. `None` means unlimited. A malformed value returns `{"doctypes": set(), "brands": set()}`, so everything is refused.
  - `doctype_in_scope(doctype: str) -> bool`
  - `brand_in_scope(brand: str) -> bool`
  - `require_doctype_in_scope(doctype: str) -> None`: raises with the exact text from Global Constraints.
  - `require_brand_in_scope(brand: str) -> None`
- Produces a helper `product_template_doctype(docname) -> str | None` in `webflow_export_v2`. It uses `web_listing_schema.WEBFLOW_PRODUCT_LINKS`, the same map `_require_sync_access` reads. A product with no template returns `None`, which is out of scope whenever `doctypes` is limited.

- [ ] **Step 1: Write the failing tests.**
  - `test_n8n_config.py`, class `SyncScope`:
    - `test_scope_unset_allows_everything`: `doctype_in_scope("ilL-Tape-Neon-Template")` and `brand_in_scope("lighting_206")` are True.
    - `test_scope_limits_doctypes_and_brands`: conf `{"doctypes": ["ilL-Fixture-Template"], "brands": ["illumenate"]}`. Fixture is True, tape is False, `illumenate` is True, `lighting_206` is False. `require_doctype_in_scope("ilL-Tape-Neon-Template")` raises `ValueError`, and its message contains `"is not enabled for spec generation and Webflow sync on this site."`.
    - `test_scope_parses_string_and_fails_closed`: the JSON-string form behaves like the dict. The value `"{not json"` makes `doctype_in_scope("ilL-Fixture-Template")` False.
  - `test_spec_sheet_job.py`:
    - `test_generate_refuses_out_of_scope_doctype`: no job is enqueued, and readiness is not called.
    - `test_plan_regeneration_skips_out_of_scope`: the skipped entry has reason `"not enabled on this site"`.
  - `test_webflow_sync.py`:
    - `test_stage_brands_refuses_out_of_scope_template`
    - `test_stage_brands_skips_out_of_scope_brand`: a fixture targeting `illumenate` and `lighting_206` gives one job for `illumenate` and `{"brand": "lighting_206", "issues": [...]}`.
  - `test_webflow_auto_push.py`:
    - `test_auto_push_refuses_out_of_scope_product`: the row is deleted, `stage_brands` is not called, and no notification is sent.
- [ ] **Step 2: Run the tests and confirm they fail.** Run `python -B -m unittest discover -s tests/portal_unit -k Scope -k scope -v`. Expected: FAIL (AttributeError `sync_scope`, or the refusal is not raised).
- [ ] **Step 3: Implement the functions listed under Interfaces and wire them in at the places named under Files.** Parse with `frappe.parse_json` when the value is a string, and catch the parse error so the result is the fail-closed set. Read the conf with the existing `_conf`.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `python -B -m unittest discover -s tests/portal_unit -v`. Expected: all tests pass, including the existing `N8nConfig`, auto-push and sync tests (the scope is unset by default).
- [ ] **Step 5: Commit.** Message: `feat(webflow): webflow_sync_scope limits spec generation and sync per site`.

### Task 2: Doctype filter on the bulk data tools

**Files:**
- Modify: `illumenate_lighting/illumenate_lighting/template_listing.py`: `refresh_all_templates(apply=False, push=False, doctypes=None)` (≈line 767).
- Modify: `illumenate_lighting/illumenate_lighting/template_link_report.py`: `link_consistency_report(apply=False, link_suggestions=False, doctypes=None)` (≈line 254) and `promote_live_templates(apply=False, doctypes=None)` (≈line 363).
- Test: the existing test modules for those files in `tests/portal_unit/`. Add new ones next to them if none exist.

**Interfaces:**
- Consumes `n8n_config.sync_scope()` from Task 1.
- Produces the rule, for all three tools: `doctypes` (a list, or a JSON string of one, as `regenerate_spec_sheets` already parses it at `spec_sheet_job.py:281-285`) limits the loop over `TEMPLATE_DOCTYPES`. When `doctypes` is omitted and `sync_scope()["doctypes"]` is set, that scope is the default. The result dict gains `"doctypes": [...]`, listing the doctypes actually covered.

- [ ] **Step 1: Write the failing tests.**
  - `test_refresh_all_templates_limits_doctypes`: with `doctypes=["ilL-Fixture-Template"]`, `frappe.get_all` is called only for that doctype, and `result["doctypes"] == ["ilL-Fixture-Template"]`.
  - `test_promote_live_templates_defaults_to_scope`: with conf scope set to fixtures, only fixture rows are in `plan["promote"]`.
  - `test_link_report_limits_doctypes`
- [ ] **Step 2: Run them and confirm they fail.** Expected: FAIL (unexpected keyword `doctypes`).
- [ ] **Step 3: Implement.** Move the `doctypes` parsing from `regenerate_spec_sheets` into a shared `template_doctypes_arg(doctypes) -> list[str]` in `web_listing_schema.py`, next to `TEMPLATE_DOCTYPES`, and use it in all four tools. Unknown doctype names raise.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `python -B -m unittest discover -s tests/portal_unit -v`. Expected: PASS.
- [ ] **Step 5: Commit.** Message: `feat(catalog): bulk template tools take doctypes and default to the sync scope`.

### Task 3: Put the staging workflow in the repo, and fix its error path

**Files:**
- Create: `n8n_workflows/spec_sync_staging.json`. It is exported from `NW0NxiyqKyeVrkOJ` and normalised. Keep: `name`, `nodes`, `connections`, `settings`. Drop: `id`, `versionId`, `activeVersion*`, `meta`, `pinData`, `scopes`, `createdAt`, `updatedAt`, `shared`, `tags`. A raw read-only export from 2026-11-23 is in the session scratchpad as `staging.json`; re-export it when you start this task.
- Modify: `n8n_workflows/lib/spec_sheet_record.js`, `n8n_workflows/lib/ill_format_data_to_inject.js` and `n8n_workflows/lib/ill_transform_to_webflow.js`, so each equals its live node's `jsCode` byte for byte.
- Create: `tests/portal_unit/spec_sync_workflow.test.cjs`. This task adds the drift tests; Task 4 adds the build tests.
- Modify: `.github/workflows/b2b-contracts.yml`: add `node tests/portal_unit/spec_sync_workflow.test.cjs` after the gallery line (≈line 36).

**n8n change, owner approval first:** in the live staging workflow, point `Stop and Error`'s message at `$('Get Spec Sheet Data')`'s error, or at the incoming `$json.error.message`, instead of the missing `$('Extract Error Message')`. Publish staging, then export. This is the only change to a live workflow in Part A.

**Interfaces:**
- Produces the file `n8n_workflows/spec_sync_staging.json`, which Task 4's builder reads.
- Produces, in the test file, a `LIB_NODES` map from snippet file to node name:

  | Snippet | Node |
  |---|---|
  | `spec_sheet_record.js` | `Get Product Info` |
  | `ill_format_data_to_inject.js` | `(ilL) Format Data to Inject` |
  | `ill_transform_to_webflow.js` | `(ilL) Transform to Webflow Format` |

- [ ] **Step 1: Write the failing tests.**
  - `test_lib_snippets_match_live_nodes`: for each `LIB_NODES` entry, the file contents (trimmed) equal that node's `parameters.jsCode` (trimmed).
  - `test_staging_error_path_has_no_missing_node_refs`: every `$('<name>')` in any node parameter names a node that exists.
- [ ] **Step 2: Run them and confirm they fail.** Run `node tests/portal_unit/spec_sync_workflow.test.cjs`. Expected: FAIL (`Extract Error Message` is missing; the snippets drift).
- [ ] **Step 3: Apply the n8n fix (approved), re-export, normalise and write the JSON. Overwrite the three lib files from the nodes.**
- [ ] **Step 4: Run the tests and confirm they pass.** Expected: PASS.
- [ ] **Step 5: Commit.** Message: `chore(n8n): check in the staging spec/sync workflow; lib snippets match the live nodes`.

### Task 4: Production workflow builder

**Files:**
- Create: `n8n_workflows/spec_sync_environments.json`. It holds the environment values as data; the builder holds no host or ID literals.
- Create: `tools/build_spec_sync_workflow.py`, a CLI in the style of `tools/build_gallery_workflow.py`.
- Create: `n8n_workflows/spec_sync_production.json`, the generated output.
- Modify: `tests/portal_unit/spec_sync_workflow.test.cjs`.
- Create: `n8n_workflows/SPEC_SYNC.md`: how to rebuild (the CLI below) and import (B4).

**Interfaces:**
- CLI: `python tools/build_spec_sync_workflow.py --env production [--source n8n_workflows/spec_sync_staging.json] [--out n8n_workflows/spec_sync_production.json]`.
- `spec_sync_environments.json` holds `{"staging": {...}, "production": {...}}`. Each entry has these keys:

  | Key | Staging | Production |
  |---|---|---|
  | `erp_origin` | `https://stagingillumenate.v.frappe.cloud` | `https://app.illumenate.lighting` |
  | `webhooks` | `{"Webhook (ilL-Publish-Job)": "staging-product-sync-v2", "Webhook": "staging-generate-spec-sheet"}` | `{"Webhook (ilL-Publish-Job)": "ill-product-sync", "Webhook": "ill-generate-spec-sheet"}` |
  | `name` | `[STAGING] Spec Gen & Webflow Sync` | `[PROD] Spec Gen & Webflow Sync` |
  | `brands` | `["illumenate", "lighting_206"]` | `["illumenate"]` |
  | `staging_guards` | `true` | `false` |

  Each entry also has `credentials`: a map from credential type and staging credential **name** to the target `{id, name}`. Use `null` to mean unbind; the runbook then binds it by hand. Production:

  | Staging credential | Production binding |
  |---|---|
  | erpNextApi `Authorization` | `{"id": "q5FbtRYh73x4yYeZ", "name": "Webflow Marketing API"}` |
  | httpHeaderAuth `STAGING Sync Secret` | `null` (the new rotated secret credential, B4) |
  | httpHeaderAuth `Wefblow ilLumenate Staging` | `{"id": "ERCkeAfdcLoATXDa", "name": "Webflow ilLumenate"}` |
  | webflowApi credentials on the template-fetch nodes | removed (plain public GET) |

- Build rules:
  1. Replace `erp_origin(staging)` with `erp_origin(env)` in every string, Code nodes included.
  2. Set each webhook node's `path`, and give it a fresh `webhookId` from `uuid5(NAMESPACE_URL, env + path)`.
  3. Remap credentials as listed.
  4. When `staging_guards` is false, remove every node whose name starts with `Staging Guard` or `(206) Staging Guard`. Reconnect each removed node's inputs to the targets of its **first (true)** output.
  5. For each brand not in `brands`, rewire the matching outputs of `Switch`, `Split by Brand` and the `Brand: *` switch nodes to a new node `Brand not enabled` (respondToWebhook, 409, body `{"success": false, "error": "brand not enabled in this environment"}`). Leave the brand's own nodes in place but disabled (`disabled: true`).
  6. Set `active: false`, the env name and the execution settings from Global Constraints.
  7. Sort nodes by name, so diffs are stable.
- Test names and assertions:
  - `test_production_has_no_staging_values`: the output JSON text matches none of `stagingillumenate`, `6aeb4d313e25a078e9393924`, `6aeb4d313e25a078e9393a2a`, `staging-`, `STAGING`, `[staging]`, `7UiZ55CCUG84sD4m`, `YXwJzXT13Mw9XMma`, `NDwBLpkiXEGmKznf`.
  - `test_production_webhooks_and_settings`:
    - the paths are exactly `ill-product-sync` and `ill-generate-spec-sheet`
    - `active === false`
    - `settings.saveDataSuccessExecution === "none"`
    - `name === "[PROD] Spec Gen & Webflow Sync"`
  - `test_guard_removal_keeps_publish_path`: from `Should Publish? (Update)` and `Should Publish? (New)`, the true branch reaches `(ilL) Publish Webflow Item (Update|New)`, and every connection target is an existing node.
  - `test_206_routes_to_brand_not_enabled`: every `lighting_206` output of the brand switches targets `Brand not enabled`, and every `(206)` node has `disabled: true`.
  - `test_transform_fails_closed_and_knows_published`: `(ilL) Transform to Webflow Format`'s code contains a `"Published"` case and a `default:` that hides (§10.6).
  - `test_template_fetch_reads_main_site`: `(ilL) Fetch Webflow Template` reads its URL from `https://illumenate.lighting/spec-sheet-templates/`.
  - `test_build_is_reproducible`: running the builder again writes byte-identical output (`execFileSync('python', [...])`).

- [ ] **Step 1: Write the failing tests above.**
- [ ] **Step 2: Run them and confirm they fail.** Run `node tests/portal_unit/spec_sync_workflow.test.cjs`. Expected: FAIL (the production file is missing).
- [ ] **Step 3: Implement the builder and the environments file, then generate `spec_sync_production.json`.**
- [ ] **Step 4: Run the tests and confirm they pass.** Run `node tests/portal_unit/spec_sync_workflow.test.cjs` and `ruff check tools/build_spec_sync_workflow.py`. Expected: PASS, with no lint errors.
- [ ] **Step 5: Commit.** Message: `feat(n8n): build the production spec/sync workflow from the staging export`.

### Task 5: Record the decisions in the source plan

**Files:**
- Modify: `docs/erpnext_spec_sheet_redesign_plan.md`:
  - §10: add a line at the top that links this plan and lists P1–P7.
  - §10.2: add `webflow_sync_scope`.
  - §10.6: replace "swap every staging value" with "run `tools/build_spec_sync_workflow.py --env production`".
  - §10.7: Q22 answered for promotion (206 is not enabled on production in this phase). Q23 still open.
  - §17: version log entry.

- [ ] **Step 1: Edit, then run `python -B tools/check_portal_templates.py`** (no doc tests exist; this only guards that nothing else broke).
- [ ] **Step 2: Commit.** Message: `docs(spec-sheet): promotion decisions for Linear Fixtures`.

### Finishing Part A

Run the full contracts locally: `python -B -m unittest discover -s tests/portal_unit` and `node tests/portal_unit/spec_sync_workflow.test.cjs`. Then use **superpowers:finishing-a-development-branch**: PR into `staging`, deploy staging, confirm nothing changed there (the scope is unset), then promote to `main`.

---

# Part B: Production runbook (operator; every write approved by the owner)

Each step has a **check** that must pass before the next step starts. "Claude may" marks read-only work Claude can do over the connected production ERP and n8n.

### B0. Prove a fixture on staging first (blocking)

§9.1 was accepted on a kit. Pick a pilot fixture that is linked, has a target brand and appears on staging2, for example one of the 59 with item IDs. Run §9.1 **B, C, D and J** on it on staging:
- Generate Spec: the page `linear-fixtures` renders delivered lumens, output options, power supplies and the part number builder.
- Sync.
- On the product page, the configured spec download.

Fix any fixture-only gaps (for example, `HIGHLIGHT_RULES` covers Extrusion Kit only, so check that fixtures need none) on staging before going on.
**Check:** the owner ticks B, C, D and J for the fixture in §9.1.

### B1. Deploy the code

- Part A merged to `main`. Production deploy on Frappe Cloud, `bench migrate`, desk assets built.
- **Check (Claude may):**
  - `getdoctype` shows the new code. The patch log contains the four §10.1 patches.
  - `webflow_promotion.check_integration_users()` returns `ok: True` for the user behind n8n credential `Webflow Marketing API`.

### B2. Backups

- Frappe Cloud: take a manual production backup.
- n8n: export `dvCvIpVLwzjgwccF` (published version `c5a1e0e8` and the saved draft) and store both outside n8n. Do not publish its draft.
- Webflow: make a site backup, and export the Products collection as CSV (the CMS content is the rollback reference).
- **Check:** the three files are stored, and each is named with the date.

### B3. Webflow production site (Designer)

- Apply the "Webflow schema diff" below. The only missing field is `web-badge` (PlainText) on Products; add it with that exact slug (§10.5).
- The `linear-fixtures` spec template page already exists (200, ids present); compare its classes and ids with staging2 once more.
- Products template page:
  - Add the `ill-fixture-type` input to the configure popup.
  - Paste `webflow_scripts/configured-spec-sheet.html` into the page custom code.
  - Remove the old `.extrusions-dwnld-submittal` and `#ill-download-spec-sheet` handlers (§10.5).
  - Publish.
- **Check:** `/products/<pilot>` loads with no console errors, and the old submittal button is gone.

### B4. n8n production workflow

1. Create a new httpHeaderAuth credential `PROD Spec Sync Secret`, header `ILL-Sync-Secret`, with a freshly generated secret. This is the rotation required by §10.1.
2. Import `n8n_workflows/spec_sync_production.json` (Workflows → Import from file). It arrives inactive.
3. Bind `PROD Spec Sync Secret` on both webhook nodes. Confirm the other bindings match the table in Task 4.
4. Do **not** publish yet.

**Check (Claude may):** `get_workflow_details` shows 0 staging strings, webhook paths `ill-*`, and `active: false`.

### B5. Production ERP configuration

- Site config:
  - `n8n_spec_webhook_url = https://illumenatelighting.app.n8n.cloud/webhook/ill-generate-spec-sheet`
  - `n8n_sync_webhook_url = …/webhook/ill-product-sync`
  - `n8n_sync_secret = <new>`
  - `n8n_sync_secret_header = ILL-Sync-Secret`
  - `webflow_environment = production`
  - `webflow_sync_scope = {"doctypes": ["ilL-Fixture-Template"], "brands": ["illumenate"]}`
  - `webflow_auto_push = 0`
  - `webflow_notify_users = [owner, Kevin]`
  - `spec_sheet_template_sites` unset
- Brand `illumenate`:
  - set `erpnext_base_url = https://app.illumenate.lighting` (P5)
  - confirm `webflow_site_id = 695c1f9a18a639365b6a31a7`
  - confirm the Products collection row is `696fc3c5c42c86528e97f413`, and the other collection rows hold main-site IDs
- **Check (Claude may):** `get_brand_config` returns those values. Generate Spec on a **kit** is refused with the scope message.

### B6. Data dry runs, scoped to fixtures (Claude may run every dry run and summarise)

1. Compare Custom Fields with the staging export (§10.4 S5); `custom_spec_custom` has never been checked on production.
2. `link_consistency_report(doctypes=["ilL-Fixture-Template"])`. Today only 36 templates are linked, against 71 products. Review `suggested_links`, then `apply` with `link_suggestions`.
3. `refresh_all_templates(doctypes=…)` as a dry run, then `apply=True, push=False`. The push is deferred to B8.
4. `adopt_hand_set_configurators`, then `payload_parity`. Fixtures only.
5. `promote_live_templates(doctypes=…)`. Review: these become Active + Live.
6. `backfill_published_on()`.
7. `regenerate_spec_sheets(doctypes="ilL-Fixture-Template")`, dry run. Note `skipped`, which includes the 10 fixtures with no Target Brand (§8.2), and `webflow_pages_needed`, which should be only `illumenate: /spec-sheet-templates/linear-fixtures`.

**Check:** the owner signs off each dry run before its `apply`.

### B7. Publish and pilot

- Publish `[PROD] Spec Gen & Webflow Sync`.
- For 1–3 pilot fixtures:
  1. Generate Spec. Check the stable link `/spec-sheets/illumenate-lighting_<template>.pdf` and its content.
  2. Sync to Webflow. Check `illumenate.lighting/products/<slug>`: specs, documents, images (absolute `app.illumenate.lighting` URLs), compatible products, badge, and the configured spec download.
- **Check (Claude may):** both n8n executions succeeded. `ilL-Publish-Job` shows Done. The Webflow item was updated, not duplicated: the same item ID as before.

### B8. Batch

- `regenerate_spec_sheets(doctypes="ilL-Fixture-Template", apply=True)`. Watch `spec_sheet_bulk_status`. n8n and Vercel get one job at a time.
- `refresh_all_templates(doctypes=…, apply=True, push=True)`. Products save, and automatic pushes queue, **held** because the switch is off.
- `auto_push_preview()`: the owner reviews the list.
- Set `webflow_auto_push = 1`. The held pushes go out within minutes.
- **Check:**
  - No new duplicate items in Webflow Products: compare the count with the B2 CSV plus newly linked products.
  - n8n error count is 0.
  - Spot-check 5 pages.

### B9. Watch and roll back

- First 48 h: check the n8n executions of the PROD workflow and the ERP Error Log ("Webflow V2 Sync", "Webflow automatic push failed").
- **Rollback (minutes):**
  1. Remove `n8n_spec_webhook_url` and `n8n_sync_webhook_url` from site config; the buttons stop with "not configured".
  2. Set `webflow_auto_push = 0`.
  3. Unpublish the PROD workflow.
  4. Restore any changed Webflow items from the B2 CSV if needed.
- The old workflow stays unpublished; it was not working, so rolling back means "no sync", as today.

### B10. Next product types (later plans)

To turn on a type:
1. Build and publish its `/spec-sheet-templates/<page>` on illumenate.lighting (it already exists for `extrusion-kit`).
2. Pass the §9.1 B/C/J on staging.
3. Add the doctype to `webflow_sync_scope.doctypes`.
4. Repeat B6–B8 with that doctype.

Recommended order: Extrusion Kits (already accepted on staging; the 8 kits missing data are filled on main, §10.4), then Tape/Neon, then LED Sheet, Driver, Controller.

206 is promoted by its own plan: a 206 staging site or a decision against one (Q22), then `brands += lighting_206`, then a rebuild with `brands` including 206.

## Webflow schema diff (staging2 vs illumenate.lighting)

Read-only comparison, 2026-11-23. Staging2 (`6aeb4d313e25a078e9393924`) is a clone of production (`695c1f9a18a639365b6a31a7`). Field IDs, Option IDs and slugs are identical; only collection and item IDs differ.

| Collection | Difference | Action (B3) |
|---|---|---|
| Products (`696fc3c5c42c86528e97f413`) | `web-badge` (PlainText) exists on staging2 only. Everything else (34 fields, `product-type` options) is identical. | Add `web-badge`, PlainText, to production Products **before B7**. Without it the sync fails with a 400 (`Field not described in schema`, the same failure the attribute-reference workflow has today). |
| Categories, Series, 13 attribute collections | Identical schemas | None |
| Galleries | Diverged, by design (gallery sync §9) | None for this plan |
| Production-only collections (Product Specifications, Configurator Options, Product Documents, IP Ratings, …, three "(old)" ones) | Not written by this sync | None |
| Site and Products-template custom code (head and footer) | Identical on both sites | None |
| HTML Embeds inside the page body | **Not readable through the API** | Designer check in B3: the configured-spec popup (`ill-fixture-type`) and `configured-spec-sheet.html`. Staging tests these with Tampermonkey (`staging.user.js`), so they are likely **missing** on production. |

**Production Products content:**
- 113 items: 45 published, 68 drafts. Every item has `erp-sync-id` equal to its slug, so the sync has written to production before.
- Linear Fixtures: 54 items, only 3 published (`lin-lgo-sw`, `opt-dt-sw`, `ill-ra01-sw`).
- **Item ID check (2026-11-23):**
  - All 59 production ERP fixture products with a stored item ID point at an existing production item. Their PATCHes will update; none goes stale.
  - The 12 without an ID would create new items: `ill-ra01..06-*`, `ill-sh01..03-dw`. None of their slugs exists in Webflow, so there will be no duplicates. Most are the 10 with no Target Brand (§8.2), which stay skipped until they get one.
  - Repeat this check right before B8; Claude may run it read-only.
- Sync writes keep the current draft/published state through the fail-closed status logic. The 51 unpublished Linear Fixture items go public only when their product's Webflow Status is Published. **The owner reviews `auto_push_preview` for exactly this before B8.**

## Out of scope (tracked separately)

- `ERPNext → Webflow Product-Attribute Reference Sync` fails on the removed `environment-ratings-filter` slug.
- Q23: the category, series and attribute workflows.
- Removing `spec_submittal_template` (§8.2; after the configured spec sheet is verified on production).
- Removing the unused Webflow fields `product-type` and `feed-lengths-json`.
- The old `dvCvIpVLwzjgwccF`: archive it after 30 days of the PROD workflow running cleanly.
