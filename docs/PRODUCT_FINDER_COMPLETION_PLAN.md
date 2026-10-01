# Product Finder — Completion Plan (handoff)


> **Implementation record — 2026-10-01:** Workstreams A–H, hardening, local tests, committed portal/public bundles and operating documentation are implemented. `main` through `2571d61` was merged into `staging`; both fixture-builder updates that arrived during implementation are included. Deployment, database migration and live-site acceptance remain the operator steps in §16 and [B2B Cloud Acceptance](B2B_CLOUD_ACCEPTANCE.md#product-finder-staging-acceptance-2026-10-01).
>
> Local verification: 384 portal Python tests; 132 fixture-builder tests; 9 React tests; 52 DOM tests across all 9 portal DOM test files (including mounting both production bundles without Node globals); YAML-builder tests; 41 Jinja templates with eight configurator modes and 18 embedded scripts; publication/reconciliation checks; zero new lint diagnostics. Playwright lists 42 desktop/mobile cases; live-site cases were not executed here. Both Vite builds are reproducible under the committed lockfile.
>
> Implementation decisions: use the brand's `webflow_site_url` for public product URLs (`get_base_url()` is the ERP host); an empty-result help request creates a support Issue because no product can honestly be linked to a verification request; caches include actor/catalog scope and an invalidation epoch so pilot/brand boundaries and deletions remain correct. Verification propagation writes only decision metadata under schedule locks and advances the schedule revision, including on locked versions; a full schedule save would reject locked historical versions or require a Finder reviewer to own the configured build. Engineering content stays unchanged. The plan's session, gate and publication defaults remain in place.

Written 2026-10-01; updated after `main` was merged into `staging` (PR #273, merge commit `579f3df`). Supersedes the PR ordering in §18 of `docs/PRODUCT_FINDER_PORTAL_IMPLEMENTATION_PLAN.md` (v2). The v2 plan still holds the product decisions; this document is the build instruction.

---

## 0. READ FIRST — how to execute this plan

> **Do the whole plan in one continuous session. Do not go phase by phase.**
>
> - The workstreams (A–I) below are an *order of work and a dependency map*, not separate deliverables. Do not stop after a workstream to report, ask for approval or wait for the user to say "next". Keep going until every item in **§17 Definition of Done** is checked.
> - The product decisions are already made (§15). Do not ask the user to re-decide them. When something is unspecified, choose the safest reasonable option, write it down, and list it in your final summary.
> - Stop and ask **only** if you are truly blocked, for example a required credential or an external system you cannot reach. Even then, finish everything else first.
> - Commit in logical units as you go (one commit per coherent change, with a descriptive message in the repo's style). **Push to `staging` after each workstream** so work is never lost. Do not open a pull request unless the user asks.
> - Your final message to the user is the only report: what was built, what was verified, which defaults you chose, and what the user must do after deploying (§16).

### 0.1 Step zero: sync branches (the main merge is already done)

`main` was merged into `staging` on 2026-10-01 in PR #273 (merge commit `579f3df`), so **do not re-do that merge**. Every conflict was resolved correctly:
- the `get_catalog_products` signature keeps both changes;
- `test_closeout.py` keeps the pilot-cohort rollout test and `main`'s commercial-lineage tests;
- `hooks.py` keeps both the `jinja` hook and the `/portal/configure-kit` redirects;
- `tools/configurator_ui/dist-preview/` is now untracked and in `.gitignore`.

At `579f3df` all of §0.3 passed: 340 Python unit tests, 42 DOM tests, the template, fixture-builder, publication and reconciliation checks, and no new lint versus `main`.

Before starting:

1. `git fetch origin main staging && git checkout staging && git pull origin staging`.
2. If `git rev-list --count staging..origin/main` is not 0, `main` has moved since: `git merge origin/main`, resolve conflicts keeping both sides' intent, and commit. Otherwise skip this step.
3. Run the full verification (§0.3), and confirm it passes before writing new code.

What `main` added that this plan uses:
- `portal/role_audit.py`, a bench-only staff role audit built from `portal/staff.py::CAPABILITIES` (see §2.4);
- `api/configuration_contract.py::string_list(value, field=...)`, which decodes list parameters sent as JSON strings. Use it for list-valued API arguments, such as multi-select answers and `line_keys`.

### 0.2 Conventions (follow exactly)

- **Python**
  - Tabs for new files. Some older files use spaces (for example `api/product_catalog.py`, `api/extrusion_kit_configurator.py`); keep their existing indentation and do not reformat whole legacy files.
  - Lint with `ruff check`. Format only files you create (`ruff format <new files>`).
  - CI's `tools/check_b2b_changes.py` fails on **new** lint diagnostics in changed files.
- **DocTypes**
  - JSON in `illumenate_lighting/illumenate_lighting/doctype/<stem>/<stem>.json`, plus `__init__.py` and a controller whose class name is the DocType name with spaces and hyphens removed (for example `ilLProductVerificationRequest`).
  - Module `ilLumenate Lighting`.
  - `tests/portal_unit/test_migration_assets.py` validates every DocType, Report and Workspace JSON against `tests/portal_unit/fixtures/frappe_v16_migration_schema.json`, plus class names, paths and link targets. Only use DocType and DocField properties present in that schema.
  - To change a DocType, edit its JSON. For new DocTypes it is easiest to generate the JSON with a script, as PR 2 did; the PR 2 generator lived in a scratchpad, so write your own.
- **Patches**
  - Add to `illumenate_lighting/patches.txt`: `[pre_model_sync]` for roles, `[post_model_sync]` for data.
  - Patches that matter on fresh installs must also be called from `illumenate_lighting/illumenate_lighting/install.py::after_install`, as PR 2 did.
  - **Never edit a patch that may already have run on staging** (`seed_product_finder`, `create_product_finder_role`). Add a new patch instead.
- **Unit tests**
  - Python: `tests/portal_unit/`, using `load_service(...)` from `tests/portal_unit/test_services.py`, which stubs `frappe`. Pass extra stub modules in its `extras` dict.
  - Controller tests: see `FakeDocument` and `controller()` in `tests/portal_unit/test_product_finder_content.py`.
  - The shared `frappe.throw` double takes no `title=` argument. Override `frappe.throw` in tests that need it.
- **DOM tests**: `tests/portal_ui/*.test.cjs` (node:test + jsdom + jquery). Copy the `setup()` helpers in `catalog.test.cjs` and `standard_products.test.cjs`.
- **Templates**: `tools/check_portal_templates.py` renders Jinja under `StrictUndefined`. Every new context variable needs `| default(...)` or a stub in that script. New Jinja globals need a stub there too (see `ill_can_view_catalog`).
- **Never** trust client-sent prices, part numbers, Items or verification state. Re-derive everything on the server, as the kit-save fix does.

### 0.3 Verification commands (run before every push; all must pass)

```bash
python -B -m unittest discover -s tests/portal_unit
python -B -m unittest discover -s tools/fixture_builder/tests
python -B tools/check_portal_templates.py          # also writes tests/portal_ui/rendered/*.html
node --test tests/portal_ui/*.test.cjs              # run AFTER the template check
node tests/portal_unit/publication_workflow.test.cjs
node --test tests/portal_unit/reconciliation.test.cjs
B2B_BASE_REF=origin/staging python -B tools/check_b2b_changes.py   # new_lint_diagnostics must be []
(cd tools/configurator_ui && npm ci && npm test && npm run build:portal && npm run build:public)  # after Workstream D
git diff --exit-code illumenate_lighting/public/product_finder   # committed bundles must be fresh
```

Install the test dependencies first, the same as CI: `pip install ruff PyYAML Jinja2 Pillow pypdf reportlab pypdfium2` and `npm ci --prefix tests/portal_ui`.

---

## 1. What already exists (do not rebuild)

### 1.1 Catalog (Phase 0, done)

| Area | Where | Notes |
|---|---|---|
| Capability and reasons | `api/product_projection.py::project_product` | Returns `capability` (`configure` / `inquiry` / `unavailable`; the catalog adds `quantity`) and `capability_reason`. Has `TEMPLATE_FIELDS` and `TEMPLATE_DOCTYPES` for Linear, Tape, Neon and Sheet. Accepts `{"lensMap": …}` metadata option rows. Takes `rollout_reason`. |
| Rollout gate | `portal/rollout.py::reason(family, public=False)` | Returns `ok`, `family_not_enabled` or `pilot_only` (from the `ill_portal_pilot_users` cohort). |
| Catalog API | `api/product_catalog.py` | Helpers `_clean_filters`, `_scope(filters, search, exclude)` and `_scope_subquery`. `_project(product, activity, **kw)` applies the rollout reason and template activity. `_standard_choices(product)`. `get_catalog_products(filters, search, page, page_size, sort)`. `get_catalog_filter_options(filters, search)` returns disjunctive facet counts. |
| Configurability report | `report/catalog_configurability` and `portal/catalog_repair.py` | Preview/Apply repair links templates through their `webflow_product` back-links. |
| Catalog page | `templates/pages/products_catalog.{py,html}`, `public/js/product_catalog.js` | `CatalogState.contextParams` already carries `finder`, `schedule`, `line_key`, `line_idx` and `draft` into product links. Has `currentFilters()`, `refreshFacetCounts()`, `applyFacetCounts()`, removable chips (`renderActiveFilterChips`), `productFamilyLabel()` and `productDetailHref()`. |
| Product page | `templates/pages/product_detail.{py,html}`, `public/js/product_detail.js` | `renderProductAction(product)` has `configure`, `standard` and `inquiry` modes. Also: `focusActionIfRequested()` (`#configure`), inline project/schedule creation (`openNewSchedulePanel`, `createScheduleFromPanel`), `rememberSchedule` / `lastSchedule`, `newKey()`, `startConfigureDraft` and `addStandardLine`. The page context has `isStaff` and `deskUrl`. |
| Nav | `templates/includes/portal_navigation.html` | Products link via the Jinja method `ill_can_view_catalog()` (`portal/jinja_methods.py`, registered in `hooks.py` `jinja`). |
| Quiz pre-fill | `portal/quiz_prefill.py::resolve(category, template, handoff)` and `match_option(answer, candidates)` | Wired into `templates/pages/configure.py`. It sets `initial_request` and `context.quiz_prefill`, and the banner in `configure.html` reports what was applied. Linear, Tape and Neon only. |
| Kit save security | `api/extrusion_kit_configurator.py::save_kit_to_schedule` | Re-validates on the server, refuses locked schedules, keeps only `KIT_SELECTION_KEYS`. `validate_kit_configuration` rejects inactive templates. |

### 1.2 Finder content (PR 2, done)

| Area | Where |
|---|---|
| DocTypes | `ilL-Product-Finder-Settings` (Single). `ilL-Finder-Question` with children `ilL-Child-Finder-Family`, `ilL-Child-Finder-Option` (fields include `rank`, `numeric_min/max`, `is_featured`, `badge_text`, `routes_to`, `is_no_preference`), `ilL-Child-Finder-Condition` and `ilL-Child-Finder-Value-Map`. `ilL-Finder-Glossary-Term`. Role `ilL Product Finder Manager`. |
| Facet registry | `portal/product_finder/facets.py`: `FACETS` (`label`, `families`, `kind` ∈ set/rank/number/range, `doctypes`, `derived`), `FAMILIES`, `COMPARISONS`, `MAPPABLE_DOCTYPES` and `needs_value_maps(facet)`. |
| Validation | `portal/product_finder/content.py::validate_question(doc, others)`. Constants `QUESTION`, `GLOSSARY`, `SETTINGS` and `KEY`. |
| Definition | `portal/product_finder/definition.py`: `current_version()`, `content_changed()`, `load_definition(include_inactive)` (cached per version) and `build_definition(version, include_inactive)`. The output already uses the **engine.js shape**: `questions[]` with `id`, `type` (single / multi / family / number / range / info), `families`, `options[]` (`value`, `label`, `image`, `color`, `featured`, `badge`, `routesTo`, `hideWhen`), `visibleWhen`, `skipWhen`; plus `glossary{}` and `settings{}`. **It does not yet include** `facet`, `match_mode`, `comparison`, `rank`, `numeric_*`, `is_no_preference`, `unknown_policy`, `relax_priority`, `verification_reason_template` or value maps. The matcher needs a richer *server* view (§4.1); keep the client payload lean. |
| Desk | `portal/product_finder/desk.py::facet_registry`, question form JS (`ill_finder_question.js`: Preview and fact-limited mapping), workspace card "Product Finder", report **Product Finder Coverage**. |
| Seed | `portal/product_finder/seed/content.json` (25 questions, 31 glossary terms) and patch `patches/seed_product_finder.py`. Images are in `illumenate_lighting/public/product_finder/options/*.webp`, served at `/assets/illumenate_lighting/product_finder/options/`. |
| Contract test | `tests/portal_unit/test_product_finder_content.py::EngineContract` runs the real `tools/configurator_ui/src/lib/engine.js` in Node against the seeded definition. |

### 1.3 Existing infrastructure to reuse

- **Sessions:** DocType `ilL-Configurator-Session`. Today it has `autoname: hash` and fields `user`, `session_token`, `product_type` (Linear Fixture / LED Tape / LED Neon), `recommended_template`, `quiz_answers` (Long Text) and `status` (Active / Used / Expired), with System Manager permissions only. `api/configurator_session.py` has `save_session` and `get_latest_session`.
- **Saving configurations:**
  - `portal/configuration.py::save(schedule_name, family, selections, idempotency_key, expected_modified, line_key, line_idx, metadata, product_slug, template, segments)`, with `FAMILIES`, `apply_artifact`, `schedule_context(name, write, lock)`, `resolve_line` and `RECEIPT`.
  - `portal/standard_products.py::choices(product)`, `prepare(product_slug, search)` and `add(product_slug, item_code, schedule_name, quantity, line_id, expected_modified, idempotency_key, location, notes)`.
- **Quotes and orders:**
  - `portal/quotes.py::request_quote`, `LINE_FIELDS` and `_snapshot`.
  - `portal/offers.py::before_submit(quotation)` (Quotation `doc_events`) and `respond(offer_name, action, …)`. On `ACCEPT` it calls ERPNext `_make_sales_order`.
  - `portal/order_intake.py::submit(schedule_name, envelope, idempotency_key)` calls `schedule.create_sales_order_result()` (`doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py`, line ~281).
- **Staff and messaging:**
  - `portal/queues.py::QUEUES`. Each entry is a tuple: `(label, capability, DocType, base filters, fields, owner field, due field)`.
  - `portal/conversations.py`: `PARENTS`, `is_staff(doc, user)` and `parent(...)`. Access is checked through `portal/files.py`: `ALLOWED_PARENTS` and `_context_access(doctype, name, ptype, user)`.
  - `portal/notifications.py::notify_user(user, preference, subject, message, reference_doctype, reference_name, event_key)`. Preferences are `notify_orders`, `notify_quotes`, `notify_drawings`, `notify_shipping` and `notify_marketing`.
  - `portal/staff.py::allowed(capability, user)` with `CAPABILITIES` (accounts, catalog, integration, sales, engineering, support, operations).
- **Projects and schedules:** `api/portal.py`: `create_project`, `create_schedule`, `get_user_projects_for_configurator` and `get_allowed_customers_for_project`.
- **Driver/controller configurator** (`api/driver_controller_configurator.py`, guest endpoints):
  - `get_{driver,controller}_configurator_init(product_slug)`
  - `get_{driver,controller}_cascading_options(product_slug, step_name, selections)`
  - `validate_{driver,controller}_configuration(product_slug, selections)`, which resolves a variant with an `item`.
  - Configuration lives in `_KINDS`, `DRIVER_STEPS` and `CONTROLLER_STEPS`.
- **Kit configurator** (`api/extrusion_kit_configurator.py`): `get_kit_configurator_init(kit_template_name)`, `get_kit_cascading_options(...)`, `validate_kit_configuration(selections)`, `save_kit_to_schedule(...)` and `get_kit_component_stock(...)`. The only UI is a Desk dialog in `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.js` (`ill_open_kit_configurator`, about lines 234–560).
- **Configurator front end** (`public/js/configurator/*`, bundled by `public/js/illumenate_web.bundle.js`):
  - `shared_configurator.js` defines `IllConfigurator.Base`, `escapeHtml`, `renderTemplateCards`, `bindScheduleContext` and the line-draft, resume and handoff logic. Lines 40–46 hold the legacy quiz alias path.
  - Other classes: `fixture_steps.js` (`Fixture`), `led_sheet_steps.js` (`LedSheet`) and `coordinator.js` (`Coordinator`).
  - `templates/pages/configure.html` branches on `is_led_sheet` / wizard / coordinator and passes `initial_request`.
- **Webflow and CORS:** `illumenate_lighting/illumenate_lighting/utils.py::after_request` with `ALLOWED_ORIGINS`, which already includes `https://illumenate-staging.webflow.io` and the staging ERP host. `api/webflow_brand.py`: `resolve_brand`, `get_base_url(brand)` and `list_active_brands`. Products have `target_brands` (brand, enabled) and `sync_targets` (brand, sync_status, webflow_collection_slug).
- **Quiz prototype** (`tools/configurator_ui/src`):
  - `lib/engine.js` (keep; extend), `lib/recommend.js`, `lib/resultObject.js`, `lib/configureHandoff.js`, `data/*.json` and `content/*.json` (all retired by this plan).
  - Components: `Wizard`, `QuestionStep`, `Results`, `CompareTable` (retire), `ProgressBar`, `SideNav`, `Tooltip` and `GlossaryTerm`.
  - Builds: `vite.config.js` (IIFE `ill-configurator.js`) and `vite.preview.config.js`.

---

## 2. Fixes to make along the way (found during research)

1. **Controller facets use attribute links, not Select values.** `ilL-Child-Controller-Template-Variant.controller_type` links to `ilL-Attribute-Controller Type`, and `mounting_type` links to `ilL-Attribute-Mounting Type` (both named by `label`). The seed options for `control_method` (`Wall Dimmer`, `Wireless Receiver`, …) and `controller_mounting` were written as Select strings.
   - In `facets.py`, set `controller_type.doctypes = ("ilL-Attribute-Controller Type",)` and `controller_mounting.doctypes = ("ilL-Attribute-Mounting Type",)`.
   - Regenerate the `attribute_doctype` Select options of `ilL-Child-Finder-Value-Map`. The test `RegistryMatchesDocTypes` enforces the sync.
   - Add a **new** patch `patches/product_finder_controller_value_maps.py`. It adds value maps to the existing `control_method` and `controller_mounting` questions only where an option has none, matched with `quiz_prefill.match_option` against the attribute records. Idempotent; never removes maps.
   - Facts read the variant links first, then fall back to the spec `controller_type` / `mounting_type` Select values (§4.2).
2. **Dealers can set line state directly.** `api/portal.py::add_schedule_line` lets a dealer set `configuration_status` on ILLUMENATE lines and add any `accessory_item`. For non-staff callers (not `allowed("sales")`):
   - Force `configuration_status = "Pending"` on ILLUMENATE lines.
   - Accept an `accessory_item` only if the Item exists, is not disabled, is a sales item and has no variants.
   - Keep current behaviour for staff, and add unit tests for both.
3. **Retire the legacy client quiz alias.** In `shared_configurator.js` lines 40–46, keep the alias path only as a fallback when `initial_request` is absent. After Workstream F, `configure.py` always resolves finder and legacy answers on the server for every family, so the alias path should never run. Leave it, but add a comment saying why.
4. **Make the Product Finder role a staff capability.** `main`'s `portal/role_audit.py` reports staff roles from `portal/staff.py::CAPABILITIES`. The PR 2 role `ilL Product Finder Manager` is not in it, so the audit cannot see who manages Finder content.
   - Add `"finder": {"ilL Product Finder Manager"}` to `CAPABILITIES`.
   - Replace the hard-coded `EDITOR_ROLES` in `portal/product_finder/desk.py` (and every new staff check in this plan) with `allowed("finder") or allowed("catalog") or allowed("sales") or allowed("engineering")`, wrapped in a helper `desk.can_edit_content(user=None)`. Keep `frappe.only_for` semantics by raising `frappe.PermissionError` when it is false.
   - `test_role_audit.py` stubs its own `CAPABILITIES`, so it is unaffected. Add one assertion that the real `CAPABILITIES["finder"]` exists.

---

## 3. New and changed files (map)

```
illumenate_lighting/illumenate_lighting/portal/product_finder/
    engine.py            # Python port of engine.js visibility + family filtering (A1)
    server_definition.py # matcher's view of questions incl. facets, maps, ranks (A1)
    facts.py             # per-product facts, cached (A2)
    matcher.py           # match(), evaluate(), companions (A3)
    prefill.py           # finder answers -> configurator selections, all families (A5)
    sessions.py          # session lifecycle + validation (B)
    verification.py      # reasons, line flags, requests, gates (C)
illumenate_lighting/illumenate_lighting/api/product_finder.py         # portal API (B)
illumenate_lighting/illumenate_lighting/api/product_finder_public.py  # guest API (H)
illumenate_lighting/illumenate_lighting/portal/kit_configuration.py   # portal kit save (G)
illumenate_lighting/illumenate_lighting/doctype/ill_product_verification_request/  (C)
illumenate_lighting/templates/pages/product_finder.{py,html}         (E)
illumenate_lighting/templates/includes/product_type_chooser.html     (E)
illumenate_lighting/templates/includes/product_finder_banner.html    (E)
illumenate_lighting/templates/includes/configurator_driver_controller_form.html (G)
illumenate_lighting/templates/includes/configurator_kit_form.html    (G)
illumenate_lighting/public/js/configurator/driver_controller_steps.js (G)
illumenate_lighting/public/js/configurator/kit_steps.js              (G)
illumenate_lighting/public/js/product_finder_portal.js               (E: banner dismiss + small helpers)
illumenate_lighting/public/product_finder/portal/  (built bundle, committed) (D)
illumenate_lighting/public/product_finder/public/  (built bundle, committed) (D)
illumenate_lighting/patches/product_finder_controller_value_maps.py  (§2.1)
illumenate_lighting/patches/product_finder_sessions_and_verification.py (B/C indexes, backfills)
illumenate_lighting/patches/backfill_kit_template_links.py           (G)
tools/configurator_ui/vite.portal.config.js, src/lib/api.js, src/lib/definition.js,
    src/components/FamilyChooser.jsx, src/components/VerificationNotice.jsx (D)
```

Changed: `facets.py`, `definition.py` (client payload additions, §D.3), `ilL-Configurator-Session` JSON and controller, `ilL-Child-Fixture-Schedule-Line` JSON, `ilL-Webflow-Product` JSON and controller (`kit_template`), `product_projection.py`, `product_catalog.py`, `catalog_repair.py` and its report, `standard_products.py`, `configuration.py`, `extrusion_kit_configurator.py`, `quotes.py`, `offers.py`, `order_intake.py` / `ill_project_fixture_schedule.py`, `conversations.py`, `files.py`, `queues.py`, `notifications.py` (use only), `configure.py` / `configure.html`, `portal.py` / `portal.html`, `portal_navigation.html`, `product_catalog.js`, `products_catalog.html`, `product_detail.js` / `.html`, `schedule.py` / `schedule.html`, `quote_request_detail.*`, `hooks.py`, `install.py`, `patches.txt`, `illumenate_web.bundle.js`, `tools/configurator_ui/*`, `.github/workflows/b2b-contracts.yml`, `tools/check_portal_templates.py`, and docs.

---

## 4. Workstream A — Matching engine

### A1. Server definition and visibility (`engine.py`, `server_definition.py`)

`server_definition.load(include_inactive=False) -> dict` is cached like `definition.load_definition`, keyed `ill_product_finder:server:{version}:{inactive}`. For every question it returns the client payload fields **plus**:

```python
{
  "id", "type", "families", "required", "visibleWhen", "skipWhen", "options": [...],
  "facet", "match_mode", "comparison", "unknown_policy", "relax_priority",
  "verification_reason_template", "label", "is_family": bool,
  "options": [{"value","label","rank","numeric_min","numeric_max","no_preference": bool,
               "routes_to","hideWhen"}],
  "value_maps": {option_value: [(attribute_doctype, attribute_value), ...]},
  "number": {"min","max","step","unit"}  # Number/Range
}
```

It also returns `settings`: `default_unknown_policy`, `verification_gate`, `results_limit`, `session_expiry_days`, `verification_title`, `verification_text`, `portal_enabled`, `public_enabled` and `public_brands`. `unknown_policy == "Use default"` resolves to the Settings value.

`engine.py` is an exact Python port of `tools/configurator_ui/src/lib/engine.js`, plus product-type filtering:

- `test_clause(clause, answers)`: the operators `eq`, `ne`, `in`, `exists`, `gt`, `gte`, `lt` and `lte` behave exactly as in engine.js. Numeric operators use `float(value)` and fail on non-numbers.
- `eval_condition(group, answers)`: `all` must all pass **and** `any` needs at least one pass. A missing group means true.
- `family_of(definition, answers)`: the answer to the question whose `type == "family"`.
- `is_visible(question, answers, family)`:
  - false when a family is chosen and the question's `families` contains neither `"Any"` nor that family (the family question itself is always visible);
  - otherwise the same as engine.js (`visibleWhen` passes and `skipWhen` does not).
- `visible_options(question, answers)`: drops options whose `hideWhen` passes.
- `prune(definition, answers)`:
  - one pass in sequence order, as engine.js does; conditions only point backwards, so one pass suffices;
  - drops answers to hidden questions;
  - drops single/multi answers that are not currently visible options.
- `route(definition, answers)`: if the family answer is an option with `routes_to == "Catalog only"`, return `{"route": "catalog", "query": {"type": "Accessory,Component"}}`. The type list for each routed option is a small constant map in `engine.py` keyed by option value; `accessories` → `Accessory,Component`.

**Also extend `tools/configurator_ui/src/lib/engine.js`** with the same family filter, so client and server agree: `isQuestionVisible(question, answers)` reads `question.families` and the family answer. Extend the `EngineContract` test with family cases (Driver answers must not show `moisture`; Linear answers must not show `load_watts`). Add a Python test that runs `engine.py` and `engine.js` on the same answer sets and asserts identical visible ids.

### A2. Product facts (`facts.py`)

`build_facts() -> list[dict]` uses batched queries only: no `get_doc` per product in a loop. Use `frappe.get_all` over child tables with `parent in [...]`, and one query per attribute master. Each product becomes:

```python
{"name","slug","title","image","product_type","family","series","product_category",
 "capability": "configure"|"quantity", "template", "facets": {facet: value_or_None},
 "sources": {facet: "attribute_link"|"template"|"spec"|"derived"}}
```

Scope: `ilL-Webflow-Product` with `is_active=1`. Capability comes from `product_catalog._project(product, activity)` with `rollout.reason(..., public=True)`, plus `_standard_choices` for quantity products. Drop products whose capability is `inquiry` or `unavailable`.

**Value types:**
- set / rank facets are a `frozenset` of ERP record names;
- number facets are a `tuple` of floats;
- `cct_range` is `(min_kelvin, max_kelvin)`;
- light_type / color_mode are a `frozenset` of answer-space values (`Static white`, `Tunable white`, `Dim-to-warm`, `Full-color`; `Analog RGB/RGBW`, `Addressable pixel (SPI)`);
- `None` means unknown.

**Sources by family** (attribute links win when present; union the rest):

| Facet | Linear Fixture (`fixture_template` → `ilL-Fixture-Template`) | LED Tape / Neon (`tape_neon_template` → `ilL-Tape-Neon-Template`) | LED Sheet (`led_sheet_template` → `ilL-LED-Sheet-Template`) | Extrusion Kit (`kit_template`, added in G) | Driver (`driver_template` variants, else `driver_spec`) | Controller (`controller_template` variants, else `controller_spec`) |
|---|---|---|---|---|---|---|
| environment_rating | attribute links "Environment Rating"; `allowed_options[option_type="Environment Rating"].environment_rating`; `allowed_tape_offerings[].environment_rating` | links; `allowed_options[Environment Rating]`; `allowed_tape_specs[].environment_rating` | `allowed_options` with `attribute_doctype == ilL-Attribute-Environment Rating` | unknown | unknown | – |
| ip_rating | unknown (→ Verify) | `allowed_options[option_type="IP Rating"].ip_rating` | `allowed_specs[].spec` → `ilL-Spec-LED-Sheet.ip_rating` | – | – | – |
| light_type / color_mode | LED packages from active `allowed_tape_offerings[].tape_offering` → `ilL-Rel-Tape Offering.led_package` | `allowed_tape_specs[].tape_spec` → `ilL-Spec-LED Tape.led_package` | sheet spec `led_package` | – | – | – |
| cct / cct_range | offering `cct` → `ilL-Attribute-CCT.kelvin` | `allowed_options[CCT].cct` → kelvin | sheet spec `cct` → kelvin | – | – | – |
| cri_min | offering `cri` → `ilL-Attribute-CRI.minimum_ra` | attribute links "CRI" → `minimum_ra` | sheet spec `cri` → `minimum_ra` | – | – | – |
| lumens_per_ft | offering `output_level` → `ilL-Attribute-Output Level.value` (tape level; note it is *before* lens loss) | `allowed_options[Output Level].output_level` → value; else tape spec `lumens_per_foot` | – (sheets are lm/ft² — leave unknown) | – | – | – |
| mounting_method | `allowed_options[Mounting Method].mounting_method` | – | – | kit `allowed_options[].mounting_method` | – | – |
| lens_appearance | `allowed_options[Lens Appearance]`; offerings' `lens_appearance` | – | – | kit `allowed_options[].lens_appearance` | – | – |
| finish | `allowed_options[Finish].finish` | Neon: `allowed_options[Finish].finish` | – | kit `allowed_options[].finish` | – | – |
| dimming_protocol | attribute links "Dimming Protocol"; else the tape specs' `input_protocol` | links; else tape spec `input_protocol` | sheet spec `input_protocol` | – | variants' `input_protocol` ∪ spec `input_protocols[].protocol` | variants' `output_protocol` ∪ spec `output_protocols[].protocol` |
| output_voltage | the tape specs' `input_voltage` | tape spec `input_voltage` | sheet spec `input_voltage` | – | variants' `voltage_output`; spec `voltage_output` | – |
| driver_wattage | – | – | – | – | variants' `wattage`; else spec `max_wattage × usable_load_factor` (default 0.8) | – |
| controller_type | – | – | – | – | – | variants' `controller_type` (attribute name); else spec `controller_type` Select |
| channels / zones | – | – | – | – | – | variants' `channels` / `zones`; else spec |
| wireless_protocol | – | – | – | – | – | variants' `wireless_protocol`; spec `wireless_protocols[].protocol` |
| controller_mounting | – | – | – | – | – | variants' `mounting_type`; spec `mounting_type` |
| application | `product_category` (Link `ilL-Webflow-Category`) for every family | | | | | |

Only active rows count (`is_active` where the child has it). LED-package derivation:
- `spectrum_type` Static White → `Static white`; Tunable White → `Tunable white`; Dim to Warm → `Dim-to-warm`; RGB, RGB+W, RGBW, RGB+TW, RGBTW → `Full-color`. Horticulture → none.
- color_mode is `Addressable pixel (SPI)` when `is_pixel`, else `Analog RGB/RGBW` for Full-color packages.

**Cache:** key `ill_product_finder:facts:{catalog_stamp}`, TTL 3600 s.
- `catalog_stamp()` is the max `modified` over `ilL-Webflow-Product`, the five template DocTypes, `ilL-Rel-Tape Offering`, `ilL-Spec-LED Tape`, `ilL-Spec-LED-Sheet`, `ilL-Spec-Driver`, `ilL-Spec-Controller` and the attribute masters used above. Run one `SELECT MAX(modified)` per DocType, combined, and cache the stamp itself for 60 s.
- Add `doc_events` `on_update` / `on_trash` for those DocTypes that call `facts.invalidate()`, which deletes the 60 s stamp key. Append to the existing hook entries where a DocType already has some (the attribute masters already have `webflow_sync_events` hooks; turn their values into lists).

The rollout gate and the dealer's pilot status are applied **per request** in the matcher (`rollout.reason(product_type)` for the current user). The shared cache never encodes per-user capability.

### A3. Matcher (`matcher.py`)

```python
match(answers, *, user=None, definition=None, facts=None, limit=None) -> dict
evaluate(answers, question_id, *, definition=None, facts=None) -> dict
companions(matches, answers, facts) -> list
```

**Algorithm for `match`:**

1. Load `definition = server_definition.load()`, then `answers = engine.prune(definition, answers)`. If `engine.route(...)` returns a catalog route, return `{"route": "catalog", "query": …}`.
2. `family = engine.family_of(...)`; keep products whose `family` equals it. With no family answer, keep all families. Then apply the per-user rollout: keep products where `rollout.reason(product_type)` is `ok`, or where the capability is `quantity`.
3. For each visible, answered question with `facet` and `match_mode != "None"`, build a **requirement**. Skip `no_preference` options and unanswered optional questions.
   - **Set facets with value maps** (`needs_value_maps(facet)`): wanted = the union of `value_maps[option]` names over the chosen option(s). If wanted is empty (an unmapped option), the requirement becomes "unknown for every product". This is surfaced as verification and is already listed on the Coverage report.
   - **Derived and no-doctype set facets** (light_type, color_mode, wireless_protocol, controller_type / controller_mounting until §2.1 lands): wanted = the normalized option value (`_norm` from `quiz_prefill`), compared with normalized product values.
   - **Rank** (`Meets or exceeds`): the needed rank is the chosen option's `rank`.
     - The product's best rank is the max `rank` over options whose value maps intersect the product's values.
     - Product values that map to no option are unknown. If the product has values but none map, the result is "unknown".
   - **Number** (`At least`): the threshold is the option's `numeric_min`, or the number answer itself. Passes when `max(product) >= threshold`.
   - **Band** (`Within band`): `[numeric_min, numeric_max]`. Passes when any product value is inside. Closeness for scoring: `min |v - mid|` over values.
   - **Range covers**: answer `{low, high}`. Passes when the product range satisfies `pmin <= low and pmax >= high`.
4. **Per product and requirement:** the result is `pass`, `fail` or `unknown` (facet `None` or empty).
   - **Hard:** `fail` excludes the product and records `excluded_by[question] += 1`. `unknown` applies the resolved policy:
     - Verify keeps the product and appends a reason;
     - Exclude drops it;
     - Include silently keeps it with no reason.
   - **Soft:** pass or fail is recorded for scoring. `unknown` with Verify appends a reason and is neutral for scoring.
   - **Reason text:** `verification_reason_template.format(answer=<option label or number>)`, falling back to `"<question label>: <answer>"`. De-duplicate.
5. **Scoring**, ported from `recommend.js`. Start at 50, then:
   - lumens band: +20 within; otherwise `max(-10, 15 - dist/spread*15)` with `spread = max(150, max-min)`, or 400 when `max >= 9000`;
   - cct and cct_range: +12 pass / −6 fail;
   - cri_min: +10 / −8;
   - every other soft facet: +4 / −2;
   - any verification reason: −5 once.

   Clamp to 0..100 and round. Sort by score descending, then `title`.
6. **Relaxation:** sort the soft requirements by `relax_priority` (None counts as 999).
   - If some hard-eligible products pass every soft requirement, the results are those (`relaxed = []`).
   - Otherwise drop soft requirements in priority order until some survive, and report `relaxed = [question labels dropped]`.
   - If none survive even then, the results are all hard-eligible products, with every soft requirement listed as relaxed.
7. **Reasons for UI:**
   - `reasons`: up to three passing requirements, for example "Wet location rated" or "IP67 or better". Each soft or hard pass renders `"{question short label}: {answer label}"`.
   - `tradeoffs`: soft fails, for example "Finish: White not offered".
8. **`no_hard_match`:** true when nothing is eligible. `eliminated_by` is the first visible question, in sequence, whose hard requirement excluded the most products, as `{question, answer}`.
9. **Companions** (`companions(top, answers, facts)`), up to 24, each as `{name, relation}`:
   - **drivers:** Driver-family products whose `output_voltage` intersects the union of the matches' `output_voltage`, and whose `dimming_protocol` intersects the answered protocol's mapped names (or the matches' protocols when no protocol was answered). Relation: "Powers 24 V with 0-10V dimming".
   - **controllers:** products whose `dimming_protocol` (outputs) intersects the answered or matched protocols. Relation: "Controls DMX512".
   - **`compatible_products`** rows of the top 10 matches (`ilL-Child-Webflow-Compatibility.related_product`). Relation: the row's `relationship_type`.

   Exclude products already in the results, and include only `configure` or `quantity` capability.
10. **Return:**

```python
{"route": None, "family": family,
 "matches": [{"name","score","reasons","tradeoffs","verify": [reason...],"best": i==0}],
 "companions": [...], "relaxed": [...],
 "counts": {"match": n, "verify": k, "excluded": x, "by_family": {...}},
 "no_hard_match": bool, "eliminated_by": {...}|None,
 "definition_version": v, "catalog_stamp": s}
```

Apply `settings.results_limit` to `matches`, but keep `counts` accurate.

**`evaluate(answers, question_id)`**, for live option counts:
- For each visible option of that question, take the pruned answers with that option set and compute **hard eligibility only** (no scoring): `{value: {"match": eligible_without_verify, "verify": eligible_with_verify}}`.
- `disabled` lists the options with zero eligible products, each with a reason naming the first eliminating question.
- Number and Range questions return only `match_count` / `verify_count` for the current answers.
- Cache in `frappe.cache()` for 600 s under `ill_product_finder:eval:{version}:{stamp}:{sha1(canonical_json(answers)+question_id)}`.

### A4. Desk "Preview matches"

- In `portal/product_finder/desk.py`, add `@frappe.whitelist() preview_matches(answers)`, staff only (`desk.can_edit_content()`, §2.4). It calls `matcher.match` with `server_definition.load(include_inactive=True)` and returns the counts plus the first 20 matches (title, score, reasons, verify) and the excluded count per question.
- In `ill_finder_question.js`, add a **Preview matches** button. It opens a dialog with a Select for this question's options and for every earlier active question's options (fetched from `definition.load_definition(include_inactive=True)` through a small whitelisted `desk.preview_definition()`), runs `preview_matches`, and renders the results table, escaping all text.

### A5. Pre-fill for every family (`prefill.py`)

`prefill_for_template(family, template, answers, definition) -> {"selections", "applied", "unmatched"}`:

- For each answered question with a facet, take the wanted ERP names (value maps) or answer values (derived facets). Pick the template's selectable option whose value is in that set. When several match, prefer the template default (`is_default`), then the first. Template option lists:
  - **Linear:** `configurator_engine.get_cascading_options_for_template` (as `quiz_prefill._linear_candidates` does), with keys `environment_rating_code`, `cct_code`, `lens_appearance_code`, `finish_code` and `mounting_method_code`. `led_package_code` comes from light_type, using spectrum type as in `quiz_prefill`.
  - **Tape / Neon:** the template's active allowed rows (`quiz_prefill._tape_neon_candidates`), with keys `environment_rating`, `cct`, `finish` and `output_level`. For output, pick the value closest to the lumen band midpoint.
  - **Driver / Controller:** the variant axis values from `driver_controller_configurator._allowed_values(template, option_type)`.
    - Driver keys: `voltage_output`, `input_protocol` and `wattage` (the smallest allowed wattage ≥ the load answer).
    - Controller keys: `controller_type`, `output_protocol`, `wireless_protocol` and `mounting_type`.
  - **Kit:** the kit template's allowed options, with keys `finish`, `lens_appearance` and `mounting_method`.
- Legacy query parameters (`moisture`, `cct`, `lens`, `finish`, `mounting`) still go through `quiz_prefill.resolve`. Keep it, and have `configure.py` choose: a `finder` token → `prefill_for_template`; otherwise legacy parameters → `quiz_prefill.resolve`.
- The result feeds `initial_request = {"template": template, "selections": selections}` and `context.quiz_prefill` (banner), exactly as today.

---

## 5. Workstream B — Sessions and portal API

### B1. Extend `ilL-Configurator-Session` (edit its JSON)

| Field | Change |
|---|---|
| `user` | Link User, **not** required. Empty means an unclaimed guest session. |
| `session_token` | Data, unique, read-only, `in_list_view`. |
| `product_type` | Select; add Extrusion Kit, Driver, Controller and Mixed; not required. |
| `source` | New. Select `Portal` / `Webflow`, default Portal. |
| `brand` | New. Link `ilL-Webflow-Brand`. |
| `definition_version` | New. Int. |
| `quiz_answers` | **JSON** (was Long Text; the column stays longtext). |
| `result_json` | New. JSON. |
| `result_stamp` | New. Data (`"{definition_version}:{catalog_stamp}"`). |
| `completed_on`, `claimed_on`, `last_seen` | New. Datetime. |
| `status` | Select `Active` / `Completed` / `Used` / `Expired`. |

- **Permissions:** System Manager full; `ilL Product Finder Manager`, `ilL Sales Review` and `ilL Catalog Publisher` read.
- **Controller `before_insert`:**
  - `session_token = frappe.generate_hash(length=32)`;
  - `user = frappe.session.user` unless Guest;
  - `last_seen = now`.
- **`hooks.py`:** add `has_permission["ilL-Configurator-Session"]` and `permission_query_conditions[...]` in `portal/product_finder/sessions.py`.
  - Staff (System Manager, Product Finder Manager, `allowed("sales")`) see all sessions.
  - Others see only `user == session user`.
  - Guests see nothing.
- **Patch `product_finder_sessions_and_verification.py`:** add DB indexes on `(session_token)` and `(user, status, modified)`.

### B2. `portal/product_finder/sessions.py`

- `get_owned(token, *, for_update=False)`: by token **and** `user == frappe.session.user`. Raises `frappe.PermissionError` with the same message for missing and foreign sessions, so tokens cannot be probed.
- `validate_answers(definition, answers) -> dict`:
  - a JSON object of at most 40 keys and 16 KB;
  - keys must be active question ids;
  - single and family values must be a visible option value;
  - multi values a list of visible option values;
  - number values finite, within min/max;
  - range values `{low, high}`, both numbers, with low ≤ high, within bounds;
  - info questions take no value.

  It returns the pruned answers and raises `frappe.ValidationError` naming the field.
- `start(import_answers=None, source="Portal") -> token`.
- `save_answers(token, answers)`: validates, stores, sets `definition_version` and touches `last_seen`.
- `complete(token)`: validates, runs `matcher.match`, stores `result_json` and `result_stamp`, sets `status = Completed` and `completed_on`, and returns the result plus `catalog_url`.
- `result(token)`: recomputes when `result_stamp` is stale.
- `claim(token)`: only an unclaimed session (`user` empty) that is under 7 days old and has `source == "Webflow"`. Sets `user`, `claimed_on` and `source` stays. Single use.
- `mark_used(token)`: `status = Used`.
- `expire_sessions()` (scheduler, daily):
  - portal sessions not seen for `session_expiry_days` → Expired;
  - unclaimed guest sessions over 7 days old → Expired;
  - Expired guest sessions over 37 days old are deleted.
- `hooks.py`: `scheduler_events["daily"] = [".../portal/product_finder/sessions.expire_sessions"]`, keeping the existing `cron` entry.

### B3. Portal API (`api/product_finder.py`)

Every endpoint is `@frappe.whitelist()`, requires login, calls `require_catalog_access()`, and throws a friendly `PermissionError` when `Settings.portal_enabled` is off. Staff (`desk.can_edit_content()`) may use `preview=1` even when the switch is off. POST endpoints use `methods=["POST"]`.

| Endpoint | Verb | Rate limit (`frappe.rate_limiter.rate_limit`) | Returns |
|---|---|---|---|
| `get_definition(preview=0)` | GET | 60/min | The client definition; `preview` includes drafts for staff. |
| `start(import_answers=None)` | POST | 20/min | `{token}` |
| `get_session(token)` | GET | 60/min | `{answers, status, stale, definition_version}` |
| `save_answers(token, answers)` | POST | 60/min | `{saved: true}` |
| `evaluate(answers, question_id)` | POST | 120/min | See A3 |
| `complete(token)` | POST | 20/min | `{catalog_url, top: first 3 matches with title/image/reasons/verify, counts, relaxed, route}` |
| `claim(token)` | POST | 10/min | `{token, catalog_url}` |
| `dismiss_banner()` | POST | 10/min | Sets the user default `ill_finder_banner_dismissed` to the current `definition_version`. |
| `request_verification(token, product_slug, schedule=None, line_key=None, message=None)` | POST | 10/min | `{request}` (§C) |

`catalog_url = "/portal/products?finder=" + token`, or `/portal/products?type=…` for a catalog route.

### B4. Legacy wrappers

`api/configurator_session.py::save_session` and `get_latest_session` become thin wrappers over `sessions`: reject Guest, validate JSON, and drop `frappe.db.commit()`. Keep their signatures for the Webflow prototype until H retires it.

---

## 6. Workstream C — "Needs verification" workflow

### C1. DocType `ilL-Product-Verification-Request`

- **Naming:** `autoname: "format:PVR-{YYYY}-{#####}"`, with `track_changes`.
- **Fields:**
  - `state`: Select `REQUESTED` / `UNDER_REVIEW` / `INFORMATION_NEEDED` / `VERIFIED` / `NOT_FEASIBLE` / `CANCELLED`, default REQUESTED, `in_list_view`, `in_standard_filter`.
  - `product`: Link `ilL-Webflow-Product`, required. `product_title`: Data, read-only. `family`: Data.
  - `finder_session`: Link `ilL-Configurator-Session`.
  - `reasons`: JSON, `[{question, question_label, answer, reason}]`. `answers_snapshot`: JSON.
  - `schedule`: Link `ilL-Project-Fixture-Schedule`. `line_keys`: Small Text (JSON list). `project`: Link `ilL-Project`. `customer`: Link Customer.
  - `requested_by`: Link User. `message`: Small Text.
  - `assigned_to`: Link User. `due_date`: Date (default: 2 business days from creation; skip Sat/Sun).
  - `resolution`: Small Text. `resolved_by`: Link User. `resolved_on`: Datetime.
- **Permissions:** System Manager, `ilL Sales Review`, `ilL Engineering` and `ilL Product Finder Manager` get read, write and report. Dealers get no DocPerm; portal access goes through services.
- **`has_permission`** (`hooks.py`): staff (`allowed("sales")` or `allowed("engineering")`) can do anything. The requester, or a user who can read the linked schedule (`access.schedule_permission(schedule, "read")`), gets read. Add matching `permission_query_conditions`.
- **Controller:**
  - `validate`: state transitions only forward (REQUESTED → UNDER_REVIEW / INFORMATION_NEEDED → VERIFIED / NOT_FEASIBLE; any → CANCELLED). Setting VERIFIED or NOT_FEASIBLE requires `resolution` and fills `resolved_by` / `resolved_on`.
  - `on_update`, when state becomes VERIFIED / NOT_FEASIBLE / CANCELLED: call `verification.propagate(self)`.
- **Desk JS:** buttons **Mark verified** and **Not feasible** (prompt for resolution), plus **Open schedule**. A list view indicator per state.
- **Wiring:**
  - Add the DocType to `conversations.PARENTS` and `files.ALLOWED_PARENTS`.
  - In `files._context_access`, add a branch calling `verification.can_access(doc, ptype, user)`: read for the requester or a schedule reader; write (reply) when the state is not final.
  - In `conversations.is_staff`, add `allowed("sales") or allowed("engineering")` for this DocType.
  - In `queues.QUEUES["verification"]`: `("Product verification", "sales", "ilL-Product-Verification-Request", {"state": ["in", ["REQUESTED", "UNDER_REVIEW", "INFORMATION_NEEDED"]]}, ["name", "product_title", "customer", "state", "assigned_to", "due_date", "modified"], "assigned_to", "due_date")`.

### C2. Schedule line fields (`ilL-Child-Fixture-Schedule-Line` JSON)

Add `verification_status` (Select `""` / Pending / Verified / Not Feasible, read-only, `in_list_view`), `verification_reasons` (Small Text, read-only, JSON), `verification_request` (Link to the request, read-only) and `finder_session` (Link `ilL-Configurator-Session`, read-only). Then:
- add them to `schedule.py`'s line dict;
- add them to `quotes.LINE_FIELDS` so the quote snapshot carries them.

### C3. `portal/product_finder/verification.py`

- `reasons_for(product_name, answers) -> list` runs `matcher` requirement evaluation for that single product: the `verify` list, with no relaxation.
- `apply_to_line(schedule, line, product_name, finder_token)`, called inside the save services **before** `schedule.save()`:
  - With no token: clear all four fields and return.
  - Load the owned session, then compute `reasons = reasons_for(product, answers)`.
  - With no reasons: clear the fields (keep `finder_session`).
  - If a VERIFIED request exists for the same `(product, finder_session)` with the same reason set: Verified, linked.
  - Otherwise: Pending. Create or reuse an open request for `(product, finder_session, schedule)`, append `line.line_key` to `line_keys`, and link it.
  - Write `verification_reasons` as JSON.
- `request(token, product_slug, schedule=None, line_key=None, message=None)`: the explicit "Ask our team to verify" action. Creates or reuses the open request (with no schedule, a general pre-sale request), posts `message` as the first conversation message, and notifies the assignee queue.
- `propagate(request_doc)`:
  - every schedule line whose `verification_request` is this request takes the matching status (VERIFIED → Verified, NOT_FEASIBLE → Not Feasible, CANCELLED → clear); save each schedule with `ignore_permissions` and a comment;
  - `notify_user(requested_by, "notify_quotes", subject, message, DocType, name, event_key=f"pvr:{name}:{state}")`;
  - post a conversation message with the resolution.
- `cancel_orphans(schedule)`: open requests whose `line_keys` no longer exist on the schedule become CANCELLED. Call it from the schedule's line-removal paths, or simply at save time from `apply_to_line`.
- `gate(schedule, stage)`: `stage` is `"issue_quote"` or `"order"`.
  - Read `Settings.verification_gate`. Throw `frappe.ValidationError("Verify or remove the lines that need verification before …")`, listing the line ids, when blocking applies:

| Gate setting | issue_quote | order |
|---|---|---|
| Before quote is issued and order is placed | block Pending / Not Feasible | block |
| Before order only | `frappe.msgprint` warning | block |
| Warning only | warning | warning |

### C4. Call sites

- **`portal/configuration.save(..., finder=None)`:** add the parameter (include it in `request_hash`). After `apply_artifact`, set `line.finder_session` and call `verification.apply_to_line(schedule, line, product_name_from_slug, finder)`. Resolve the product from `product_slug`, or from the template's `webflow_product`. Also `sessions.mark_used(finder)`.
- **`standard_products.add(..., finder=None)`, `standard_products.add_configured(..., finder=None)` (G2) and `kit_configuration.save(..., finder=None)` (G3):** same pattern.
- **`offers.before_submit`:** after the existing checks, `verification.gate(schedule, "issue_quote")`.
- **`offers.respond`** with `action == "ACCEPT"`: `verification.gate(schedule, "order")` before `_make_sales_order`.
- **`ill_project_fixture_schedule.create_sales_order_result`:** `verification.gate(self, "order")` at the top. This covers order intake and Desk.
- **`quote_from_schedule.add_schedule_to_quotation`:** `frappe.msgprint` listing pending lines; never blocks.

### C5. Portal display

- **`schedule.html` line rows:** a badge next to the product type. "Verification pending" (amber), "Verified by ilLumenate" (green) or "Not feasible — see message" (red, linking to the request's conversation). Add a schedule-level banner when any line is pending.
- **`quote_request_detail.html`:** "N lines awaiting verification", from the snapshot.
- **Product page:** see F3.

---

## 7. Workstream D — React Finder UI (`tools/configurator_ui`)

### D1. Remove and keep

- **Delete:** `src/data/products.seed.json`, `src/data/competitors.sample.json`, `src/data/attributes.seed.json`, `src/lib/recommend.js`, `src/lib/resultObject.js`, `src/lib/configureHandoff.js`, `src/components/CompareTable.jsx`, `src/content/*.json`, `src/assets/*.jpg`, and `src/assets/README.md` (images now come from server URLs).
- **Keep and extend:** `src/lib/engine.js`. It now receives questions at runtime: replace the static import with `let QUESTIONS = []; export function setDefinition(def) { QUESTIONS = def.questions; }`. Drop `LUMENS_BANDS` and `lumensBandFor`; lumen bands now live on the option `numeric_min/max` and are used only on the server. Add the family filter (A1). Update the `EngineContract` test's string replacement to match the new code; inject the definition with `setDefinition` instead.

### D2. New modules

- **`src/lib/api.js`:** `createClient(config)` returns `getDefinition`, `start`, `getSession`, `saveAnswers`, `evaluate`, `complete`, `claim` and `requestVerification`.
  - **portal:** `fetch('/api/method/illumenate_lighting.illumenate_lighting.api.product_finder.<fn>', { credentials: 'same-origin', headers: { 'X-Frappe-CSRF-Token': config.csrfToken, 'Content-Type': 'application/json' } })`.
  - **public:** `fetch(config.apiBase + '/api/method/illumenate_lighting.illumenate_lighting.api.product_finder_public.<fn>', { credentials: 'omit' })`, with GET for `get_definition` and `evaluate`.
  - Unwrap `message` and surface `_server_messages` errors.
- **`src/lib/definition.js`:** `loadDefinition(client)` calls `engine.setDefinition` and returns `{questions, glossary, settings}`.
- **`src/components/FamilyChooser.jsx`:** the featured option (`featured: true`) renders as a large card spanning two columns (full width on mobile), with its image, `badge` pill and description. The other options use a 3-column grid. Below it, a text button "I'm not sure" selects the featured value. Each card is a `button` with `aria-pressed`, and the group has `role="radiogroup"`.
- **`src/components/VerificationNotice.jsx`:** the amber notice, using `settings.verification_title` / `verification_text`, with `{reasons}` replaced by a comma-joined list.

### D3. `definition.py` client payload additions

Add the fields the UI needs:
- option `noPreference` (from `is_no_preference`);
- question `glossaryKey` (already present);
- settings `verification_title` / `verification_text` (already present) and `banner_*` (already present).

Keep facets, maps and ranks out of the client payload.

### D4. Changes to existing components

- **`Wizard.jsx`:**
  - props `config`;
  - on mount `loadDefinition`, then resume (`sessionToken`), claim (`claimToken`), or `start()`;
  - debounced `saveAnswers` (500 ms) after each change;
  - `evaluate(answers, currentQuestion.id)`, debounced 150 ms; keep the last counts while loading;
  - the family answer filters questions through `engine.visibleQuestions`;
  - an option with `routesTo === 'catalog'` immediately calls `complete()` and navigates to the returned catalog URL;
  - move focus to each newly revealed question heading;
  - `prefers-reduced-motion` makes `scrollIntoView` instant;
  - sticky offset: `top: var(--ill-finder-top, 80px)`;
  - remove the prototype footer;
  - preview mode shows a "Draft" badge on drafts.
- **`QuestionStep.jsx`:**
  - delete the static image imports and `imageMap`; use `option.image` (URL) or the `option.color` swatch;
  - show counts: "12 products · 3 need a check";
  - disabled options show a reason from `evaluate().disabled`;
  - `noPreference` options never disable;
  - number and range inputs stay as they are;
  - `family` type renders `FamilyChooser`.
- **`Results.jsx`**, rewritten:
  - a heading with the total count and counts per family; the relaxation notice; the top three cards (image, title, reasons, verification chips); `VerificationNotice` when any top match needs verification;
  - **portal:** "See matching products" (→ `catalog_url`), "Configure the top match now" (→ `/portal/products/<slug>?finder=<token>#configure`), "Edit answers" and "Start over";
  - **public:** product cards linking to the Webflow URLs returned by the public API, plus "Configure & add to a project (dealers)" → `claim_url`;
  - `no_hard_match`: "No products match … (eliminated by Q)" with "Change that answer" (scroll to it) and "Ask our team" (portal: `requestVerification` without a product; public: mailto from settings, if present).
- **`App.jsx` / `main.jsx`:** pass `config` down. `mount(el, opts)` merges `window.ILL_CONFIGURATOR_CONFIG`.

### D5. Builds, tests and CI

- **`vite.portal.config.js`:** IIFE library build of `src/main.jsx` with `outDir: '../../illumenate_lighting/public/product_finder/portal'`, `emptyOutDir: true`, `base: '/assets/illumenate_lighting/product_finder/portal/'`, `cssCodeSplit: false`, `fileName: () => 'ill-finder.js'`, and asset name `ill-finder.[ext]`.
- **`vite.config.js` (public):** same, with `outDir: '../../illumenate_lighting/public/product_finder/public'`.
- **`package.json` scripts:** `"build:portal"`, `"build:public"`, `"test": "vitest run"`. Add dev dependencies `vitest` and `jsdom`, and regenerate `package-lock.json`.
- **Vitest tests (`src/**/*.test.jsx`):**
  - engine family filtering;
  - `FamilyChooser`: featured card first, keyboard order, "I'm not sure" selects Linear;
  - Wizard autosave debounce and the evaluate call;
  - Results: portal and public CTAs, no `CompareTable` anywhere (assert the module does not exist);
  - `routesTo` catalog navigation.
- **Commit the built files.** Frappe Cloud runs only `bench build` (esbuild), not Vite or Tailwind.
- **`.github/workflows/b2b-contracts.yml`:** add the step "Product Finder bundles are fresh": `npm ci --prefix tools/configurator_ui && npm test --prefix tools/configurator_ui && npm run build:portal --prefix tools/configurator_ui && npm run build:public --prefix tools/configurator_ui && git diff --exit-code illumenate_lighting/public/product_finder`.
- **Style isolation:** keep Tailwind's `important: '#ill-configurator-root'` and `preflight: false`. Add scoped resets in `src/index.css` for `button`, `input`, `label` and `h1`–`h4` inside `#ill-configurator-root`, so the portal's Bootstrap does not restyle them. Check the rendered portal page in a Playwright screenshot (§13).

---

## 8. Workstream E — Portal page, banner, nav, product-type chooser on `/portal/configure`

- **Route:** in `hooks.py`, add `{"from_route": "/portal/product-finder", "to_route": "product_finder"}`.
- **`templates/pages/product_finder.py`:**
  - Guest → `/login?redirect-to=<current url>` (keep `claim`), using the same helper pattern as `products_catalog.py`.
  - No catalog access → `/portal/request-dealer-access`.
  - `portal_enabled` off and not staff preview → `/portal/products`.
  - Context: `session_token` (only if `?session=` is owned by the user), `claim_token` (`?claim=`), `preview` (staff and `?preview=1`), `csrf_token = frappe.sessions.get_csrf_token()`, `title = "Product Finder"`, `no_cache = 1`.
- **`product_finder.html`:**
  - extends `templates/web.html` and includes `portal_navigation.html`;
  - contains `<div id="ill-configurator-root" data-ill-manual-mount></div>`;
  - `<link rel="stylesheet" href="/assets/illumenate_lighting/product_finder/portal/ill-finder.css">` and `<script src="/assets/illumenate_lighting/product_finder/portal/ill-finder.js"></script>`;
  - an inline mount: `IllConfigurator.mount('ill-configurator-root', {mode:'portal', csrfToken, sessionToken, claimToken, preview, catalogUrl:'/portal/products'})`, with all values via `| tojson`.
- **Banner (`templates/includes/product_finder_banner.html`)**, included from `portal.html` between the hero and the cards.
  - `portal.py` context: `finder_banner = None` unless the user can view the catalog, `portal_enabled` and `banner_enabled` are on, and `frappe.defaults.get_user_default("ill_finder_banner_dismissed") != str(version)`. Then a dict of headline, text, CTA, image and `resume`.
  - `resume` is the latest Active session for the user, with its progress percentage (answered visible required / total) and URL `/portal/product-finder?session=<token>`.
  - Markup: an image, then headline and text, then the CTA ("Start the Product Finder", or "Resume (N% done)"), a "Browse catalog" link and a close button (`aria-label="Dismiss"`). On mobile it stacks.
  - `public/js/product_finder_portal.js` (add to `illumenate_web.bundle.js`): the close button POSTs `dismiss_banner` and fades the banner out.
  - When the banner is dismissed, show a compact "Product Finder" card in the cards row instead.
- **Nav:** in `portal_navigation.html`, add `{% if ill_finder_enabled() %}<a href="/portal/product-finder">Product Finder</a>{% endif %}`. The new Jinja method `ill_finder_enabled()` (`jinja_methods.py`) returns can-view-catalog **and** `portal_enabled`. Register it in `hooks.py` `jinja.methods` and stub it in `tools/check_portal_templates.py`.
- **Catalog header:** a "Help me choose" link, shown when the finder is enabled.
- **Product-type chooser on `/portal/configure`:**
  - New include `templates/includes/product_type_chooser.html`, rendered by `configure.html` when `show_type_chooser` is set.
  - `configure.py` sets `show_type_chooser = not frappe.form_dict.get("category") and not template_code and initial_request is None`. When it is true, skip the template fetch and render only the chooser.
  - **Content:** read the active Family chooser question from `definition.load_definition()`: its options, images, badge and featured flag. This keeps it identical to the quiz. Fall back to a static list if there is no such question.
  - **Links:** `/portal/configure?category=<family>` plus the current `schedule`, `line_key`, `line_idx` and `draft`. Families without a configurator (accessories) link to `/portal/products?type=Accessory,Component`.
  - Add a footer link "Not sure what you need? Take the Product Finder" (when enabled).
  - Replace the LED Sheet-only category pills (`configure.html` lines ~45–55) with a compact "Change product type" link back to the chooser, keeping the schedule parameters.
- **`tools/check_portal_templates.py`:** render `product_finder.html`, the banner (with and without resume) and the chooser, and assert escaping.

---

## 9. Workstream F — Catalog and product page with finder context

### F1. Catalog API (`api/product_catalog.py`)

- `get_catalog_products(..., finder=None, view=None)`:
  - With `finder`: `result = sessions.result(token)` (recomputing when stale). `names = [m["name"] for m in result["matches"]]`. Add the condition `` `tabilL-Webflow-Product`.name IN %(finder_names)s `` (an empty list returns an empty page).
  - `sort == "relevance"` (default with a finder): `ORDER BY FIELD(`tabilL-Webflow-Product`.name, %(n0)s, %(n1)s, …)`, parameterized, falling back to `product_name`.
  - Attach `match: {score, reasons, tradeoffs, verify, best}` to each product. Top-level `finder: {token, family, answer_chips: [{question_id, label}], relaxed, counts, companions_count, route}`.
  - `view == "companions"`: restrict to the session's companion names, and attach `relation`.
  - Attribute filters and search still narrow within the set (`_scope` is unchanged).
- `get_catalog_filter_options(filters, search, finder=None)`: when a finder is present, AND `name IN finder_names` into every scope subquery. Thread an optional `restrict_names` through `_scope`.
- `answer_chips`: build from the session answers and the client definition (question `shortLabel` plus option label, or the number with its unit). Skip no-preference answers.

### F2. Catalog page (`products_catalog.html`, `product_catalog.js`)

- When `CatalogState.contextParams.finder` is set, send `finder` with both API calls.
- **Finder banner** (`#finderBanner`):
  - "Showing **N** products that fit your answers · K need a quick check with our team";
  - the answer chips;
  - links **Edit answers** (`/portal/product-finder?session=<token>`), **Show all products** (remove `finder` from `contextParams` and the URL, then reload) and **Start over** (`/portal/product-finder`);
  - the relaxation notice.
- **Tabs:** Recommended (N) | Drivers, controllers & accessories (M) (`view=companions`) | All products (drops the finder).
- **Cards in finder mode:**
  - a "Best match" badge;
  - up to two green reason chips;
  - an amber "Verify with our team" chip with a `title` listing the reasons;
  - the companion relation text in the companions tab.
- **Empty finder result:** "No products match **…**", with **Edit answers** (`?session=<token>#<eliminated question>`) and **Ask our team** (calls `request_verification` without a product, then shows a confirmation).
- **DOM tests:** the banner, tabs, chips, links carrying `finder`, the companions view request and the empty state.

### F3. Product page (`product_detail.py`, `.html`, `.js`)

- `get_catalog_product_detail(product_slug, finder=None)`: with an owned finder token, attach `match` (from the stored result, or recomputed for this product only with `verification.reasons_for` plus the matcher reasons) and `companions` (up to 6, with relation, image, title and capability).
- **UI when `?finder` is set:**
  - a **"Why this product fits"** box (reasons and trade-offs);
  - the **verification callout** (title, text, reasons) with **Ask our team to verify now**, which opens a message textarea and calls `request_verification(token, slug, schedule?, line_key?)`, then shows "Request PVR-… sent";
  - a breadcrumb "← Your matches" (`/portal/products?finder=…`);
  - **Pairs well with**: companion cards, each with "Add to schedule" (quantity) or "Configure" (configure), both carrying `finder`.
- **Wiring `finder` through:**
  - `configureHref` adds `finder`;
  - `startConfigureDraft` stores `finder` in the draft metadata;
  - `addStandardLine` sends `finder`;
  - `standard_products.add` accepts it (C4).
- `configure.py`: read `finder` (owned session) → `prefill_for_template(...)` → `initial_request` and the banner. Pass `finder` into the page context so the configurator's save sends it. Add `finder` to the context passed to `Coordinator`, `Fixture`, `LedSheet` and the new G classes, and include it in their save payloads (`portal/configuration.save(..., finder=)`).
- **After saving from a finder flow**, the configurator's success panel shows **"Back to your matches"** next to the existing "View schedule".

---

## 10. Workstream G — Driver, controller and extrusion kit configurators

### G1. Projection, catalog and data

- **`product_projection.py`:** `TEMPLATE_FIELDS` += `"Extrusion Kit": "kit_template"`, `"Driver": "driver_template"`, `"Controller": "controller_template"`. `TEMPLATE_DOCTYPES` += `ilL-Extrusion-Kit-Template`, `ilL-Driver-Template` and `ilL-Controller-Template`. The `FAMILY_ALIASES` in `configuration_contract.py` gets identity entries for the three families. `configure_url` for these = `/portal/configure?category=<family>&template=<code>&product_slug=<slug>`.
- **Driver and controller products with `is_configurable` and an active template become `configure`.** Products with only a `*_spec` (no template) stay `quantity` through `standard_products.choices`.
- **`ilL-Webflow-Product` JSON:** add `kit_template` (Link `ilL-Extrusion-Kit-Template`, `depends_on: eval:doc.product_type=='Extrusion Kit'`). In the controller, add `_update_template_backlink("ilL-Extrusion-Kit-Template", "kit_template")` in `on_update`, mirroring the driver and controller back-link calls.
- **Patch `backfill_kit_template_links.py`:** for each kit template with `webflow_product`, set the product's `kit_template` if empty (`frappe.db.set_value`; no save, to avoid regenerating options). Log conflicts.
- **`catalog_repair.py`** and the **Catalog Configurability** report: include the new families. `TEMPLATE_DOCTYPES` drives both, so this is mostly automatic. Update the report's product-type filter options and the `how_to_fix` text.
- **`configure.py`:** `_normalize_product_category` adds Extrusion Kit, Driver and Controller (and plurals or slugs). `title_map` adds "Configure Extrusion Kit", "Configure Power Supply" and "Configure Controller". `rollout.require_family` already handles them.

### G2. Driver and controller (portal)

- **Partial `configurator_driver_controller_form.html`:**
  - the shared schedule-target card, reusing what `configurator_led_sheet_form.html` renders (`bindScheduleContext`);
  - a step list container;
  - a validation summary (part number, variant, MSRP when `show_pricing`);
  - a fixture-type / location / qty / notes block that follows the draft pattern;
  - a save button.
- **`public/js/configurator/driver_controller_steps.js`:** class `IllConfigurator.DriverController(rootEl, context)` extends `Base`. `context.kind` is `Driver` or `Controller`, alongside `product_slug`.
  - init: `get_{kind}_configurator_init(product_slug)` → render each active step as pill buttons (radio semantics), with glossary tooltips for protocol terms;
  - on change: `get_{kind}_cascading_options(product_slug, step_name, selections)` → disable unreachable values;
  - when all steps are chosen: `validate_{kind}_configuration` → show the variant, part number, Item and price;
  - restore from `initial_request.selections` (pre-fill A5);
  - save → `standard_products.add_configured`.
  - Register in `illumenate_web.bundle.js`.
- **`portal/standard_products.add_configured(product_slug, selections, schedule_name, quantity, line_id, expected_modified, idempotency_key, location=None, notes=None, finder=None)`** (POST, `@atomic_build`). Mirror `add`:
  - receipts, idempotency key, schedule lock/state checks;
  - re-run `driver_controller_configurator._validate_configuration(kind, product_slug, json.dumps(selections))` on the server;
  - require `is_valid`, and that the variant's `item` is in `choices(product)`;
  - write an ACCESSORY line with `variant_selections = canonical_json({product_slug, template, selections, variant_code, item_code})`;
  - `verification.apply_to_line`.
- **`configure.html`:** a new branch `{% elif product_category in ('Driver','Controller') %}` that includes the partial and instantiates `IllConfigurator.DriverController` with the same context keys as the others, plus `kind`, `product_slug` and `finder`.

### G3. Extrusion kit (portal)

- **Partial `configurator_kit_form.html`** and **`public/js/configurator/kit_steps.js`**: class `IllConfigurator.Kit`, ported from the Desk dialog (`ill_project_fixture_schedule.js` `_show_kit_configurator_dialog`, `_refresh_kit_cascading`, `_update_kit_preview`):
  - template picker (`renderTemplateCards` with the kit templates from `get_kit_configurator_init()`), unless `template` is given;
  - steps: Finish → Lens appearance → Mounting method → End cap style → End cap color, with cascading through `get_kit_cascading_options`;
  - a live composition preview and stock (`get_kit_component_stock`; quantities only for dealers who are allowed to see stock, the same rule as `schedule.py::_compute_kit_stock_for_line`);
  - validate through `validate_kit_configuration`;
  - save through `portal/kit_configuration.save`.
- **`portal/kit_configuration.save(schedule_name, selections, idempotency_key, expected_modified, line_key=None, line_idx=None, metadata=None, finder=None)`** (POST, `@atomic_build`):
  - `require_catalog_access`; `schedule_context(write=True, lock=True)`; receipt and idempotency like `configuration.save`;
  - `expected_modified` must match;
  - `resolve_line`;
  - re-validate (`validate_kit_configuration(selections)`, restricted to `KIT_SELECTION_KEYS`);
  - write the line exactly as `save_kit_to_schedule` does today (`product_type = "Extrusion Kit"`, `ill_item_code`, `kit_template`, `variant_selections` with server pricing) plus `line_id`, `location`, `qty` and `notes` from the metadata;
  - `verification.apply_to_line`.
- **Refactor `save_kit_to_schedule`** to call the same internal `_write_kit_line(schedule, line, result)` helper, so there is one writer. Keep its public signature for compatibility.
- **`configure.html`:** add an `{% elif product_category == 'Extrusion Kit' %}` branch.

### G4. Remaining routes

`main`'s redirect sends `/portal/configure-kit/...` to `/portal/configure`. Change the target to `/portal/configure?category=Extrusion%20Kit` (in `website_redirects` in `hooks.py`).

---

## 11. Workstream H — Public (Webflow) quiz on live data

### H1. `api/product_finder_public.py`

Every endpoint is `@frappe.whitelist(allow_guest=True)` and rate-limited. CORS comes from the existing `utils.after_request` (`ALLOWED_ORIGINS`). Throw `PermissionError` unless `Settings.public_enabled` is on and `brand` is in `Settings.public_brands`; resolve the brand with `webflow_brand.resolve_brand`.

| Endpoint | Verb | Limit | Notes |
|---|---|---|---|
| `get_definition(brand)` | GET | 60/min/IP | The client definition without drafts. Rewrite every option `image` and `settings.banner_image` to an absolute URL (`frappe.utils.get_url(path)`). |
| `evaluate(brand, answers, question_id)` | GET | 120/min/IP | `answers` is a JSON query parameter of at most 4 KB. Facts restricted to **published** products. |
| `complete(brand, answers)` | POST | 10/min/IP | Validates, then creates a session with `source = "Webflow"`, `brand` and empty `user` (insert with `ignore_permissions`). Runs the match on published products. Returns `{token, claim_url, matches: [{title, image (absolute), url, family, reasons, verify}], counts, relaxed, route}`. **No prices, stock or Items.** |

- **Published** means: `is_active`; capability `configure` or `quantity`; a `target_brands` row for the brand with `enabled`; and a `sync_targets` row for the brand with `sync_status == "Synced"` and a `webflow_collection_slug`.
- `url = webflow_brand.get_base_url(brand).rstrip('/') + '/' + collection_slug + '/' + product_slug`.
- `claim_url = frappe.utils.get_url('/portal/product-finder?claim=' + token)`.
- Guest requests use `credentials: 'omit'`, so they always run as Guest. That avoids CSRF failures for visitors who are logged in to the ERP.
- Add `"https://illumenate.webflow.io"` and any production Webflow domains you find in `webflow_brand` data to `ALLOWED_ORIGINS` **only if** they are missing.

### H2. Claim flow

- `/portal/product-finder?claim=<token>`:
  - logged-out users are sent to log in and come back;
  - non-dealers are sent to `/portal/request-dealer-access?claim=<token>` (pass it through and show "Your quiz answers are saved");
  - dealers: the page calls `claim(token)` and then navigates to the catalog URL.
- After dealer access is approved, the first visit to the Product Finder with a remembered claim (`localStorage` `ill-finder-claim`) claims it.

### H3. Webflow embed and retirement

- The public bundle is `illumenate_lighting/public/product_finder/public/ill-finder.js` and `.css`, served from the ERP host.
- **Docs:** update `docs/WEBFLOW_INTEGRATION_GUIDE.md` and `tools/configurator_ui/README.md` with the embed snippet:
  - `<div id="ill-configurator-root" data-ill-manual-mount></div>`;
  - the CSS and JS tags pointing at `https://<erp>/assets/illumenate_lighting/product_finder/public/ill-finder.{css,js}`;
  - `IllConfigurator.mount('ill-configurator-root', {mode:'public', apiBase:'https://<erp>', brand:'<brand code>'})`.
- Delete `vercel.json` and `vite.preview.config.js` (the prototype preview), and `dist-preview/` if it is still tracked.
- Remove the "Webflow quiz → `/portal/configure` legacy parameters" path from the docs. Keep the server-side legacy conversion for old links.

---

## 12. Hardening (do these too)

1. `add_schedule_line` restrictions (§2.2).
2. **Session tokens:** never put a token in logs or error messages. Every session endpoint compares the owner. Claim is single use.
3. **Rate limits** on every new whitelisted endpoint (tables above).
4. **Escaping:** every Jinja value goes through autoescape or `| tojson`. All JS rendering uses `escapeHtml` / `textContent`. React escapes by default; never use `dangerouslySetInnerHTML` (glossary `learn_more` is Text Editor HTML: render it through a whitelist sanitizer such as `DOMPurify`, added as a dependency, or strip tags on the server with `frappe.utils.sanitize_html` in `definition.py`. **Choose the server option.**)
5. **Swatch colors** are already validated (`content.SWATCH`). In React, set them only through the `style` prop, never as raw CSS strings.
6. **Performance:** `build_facts` must stay under 1 s for 500 products. Add a unit test with 500 synthetic products asserting a bounded number of `frappe.get_all` / `frappe.db.sql` calls (no per-product queries).

---

## 13. Tests (all required)

| Layer | File | Must cover |
|---|---|---|
| Python | `test_product_finder_engine.py` (new) | `test_clause` for every operator; all/any groups; family filtering; prune (hidden question, hidden option, stale option); catalog `route`; **parity with engine.js** on 10 answer sets (run node; skip if node is missing). |
| Python | `test_product_finder_facts.py` (new) | Each family's sources (tables in A2) from stubbed `get_all` rows; attribute links win; LED-package derivation; inactive rows ignored; capability filter; cache key per stamp; invalidation; **query count bounded for 500 products**. |
| Python | `test_product_finder_matcher.py` (new) | Hard pass/fail; unknown under Verify / Exclude / Include; rank via value maps; At least; Within band and closeness; Range covers; no-preference skip; unmapped option → unknown; scoring order (verify −5); relaxation order and `relaxed` labels; `no_hard_match` / `eliminated_by`; companions (driver voltage and protocol, controller protocol, compatible products, excludes duplicates); per-user rollout `pilot_only`; `results_limit` keeps counts; `evaluate` counts and disabled reasons; cache keys. |
| Python | `test_product_finder_prefill.py` (new) | Every family maps only template-allowed values; driver wattage picks the smallest ≥ load; legacy parameters still use `quiz_prefill`. |
| Python | `test_product_finder_sessions.py` (new) | Answer validation (every rule in B2); owner-only access with indistinguishable errors; start/save/complete/result staleness; claim (guest-only, age, single use); expiry job; has_permission and query conditions. |
| Python | `test_product_finder_api.py` (new) | Every endpoint: login, catalog access, the `portal_enabled` switch, the staff preview override, POST-only, arguments, return shapes. |
| Python | `test_product_finder_public.py` (new) | Disabled switch / unknown brand → PermissionError; published-only filter; absolute image URLs; no price, stock or Item keys anywhere in the response (recursive assertion); claim URL; the 4 KB cap. |
| Python | `test_product_verification.py` (new) | DocType transitions; `apply_to_line` (no token, no reasons, reuse VERIFIED, create/reuse open request, line_keys); `propagate` updates lines and notifies; `cancel_orphans`; `gate` for each setting × stage; call sites (`offers.before_submit`, `respond` ACCEPT, `create_sales_order_result`); `quotes.LINE_FIELDS` includes the new fields; conversation access (`files._context_access`, `is_staff`); queue registration. |
| Python | `test_configurators_g.py` (new) | Projection for the new families; `kit_template` back-link and backfill; `add_configured` re-validation and Item-in-choices; `kit_configuration.save` (forged payload ignored, receipts, idempotency, lock); `save_kit_to_schedule` uses the shared writer; configure-page category normalisation. |
| Python | update `test_contracts.py`, `test_catalog_facets.py`, `test_product_choices.py`, `test_product_finder_content.py` | Finder-scoped catalog queries (`name IN`, relevance `FIELD` ordering, companions view); facet options scoped to finder; controller facets registry change; the new client payload fields. |
| Python | `test_add_schedule_line.py` (new) | §2.2 for dealer and staff. |
| DOM | `tests/portal_ui/product_finder.test.cjs` (new) | Banner render, dismiss POST, resume label; configure chooser links keep schedule/draft; Linear featured first. |
| DOM | update `catalog.test.cjs` | Finder banner, tabs, chips, companions, empty state, `finder` carried in every request and link. |
| DOM | update `standard_products.test.cjs` | Why-fits box, verification callout, Ask our team, pairs-well-with, `finder` in configure href, draft and `add` args. |
| DOM | `tests/portal_ui/driver_controller.test.cjs`, `kit.test.cjs` (new) | Steps render from init; cascading disables; validate summary; save payload; restore from `initial_request`. |
| React | `tools/configurator_ui/src/**/*.test.jsx` (vitest) | D5 list. |
| Templates | `tools/check_portal_templates.py` | `product_finder.html`, banner, chooser, the new configure branches (Driver, Controller, Kit), schedule badges, quote request counts. |
| E2E | `tests/portal_e2e/portal.spec.cjs` | Add specs (they are listed in CI, not run): dealer banner → Linear → Outdoor/Wet/IP67/Static/Surface/0-10V → catalog verification chip → product → configure pre-filled → save → schedule "Verification pending" → request quote; driver path; kit path; accessories route; `/portal/configure` chooser; public → claim → filtered catalog. |

---

## 14. Docs to update

- `docs/PRODUCT_FINDER_PORTAL_IMPLEMENTATION_PLAN.md`: add a "Status" line at the top pointing to this file, and mark each section implemented.
- `docs/DEALER_ROLE.md`: a section on the Product Finder (dealer view).
- `docs/B2B_STAFF_OPERATIONS.md`:
  - add `ilL Product Finder Manager` to the role table and to the role-assignment checklist (the checklist added by `main` for `role_audit.report`);
  - editing questions;
  - reading the Coverage and Configurability reports;
  - working the verification queue (states, resolution, what dealers see);
  - the verification gate setting.
- `docs/WEBFLOW_INTEGRATION_GUIDE.md` and `tools/configurator_ui/README.md`: the new embed and the portal mode.
- `docs/B2B_CLOUD_ACCEPTANCE.md`: add the Product Finder acceptance scenarios (§16).

---

## 15. Decisions already made (do not re-ask)

1. Missing product data → **show with a positive verification warning**: "we most likely can do it, but our team must verify before you continue". The gate blocks issuing a quote and placing an order (configurable in Settings). Dealers may keep configuring and may request quotes.
2. **Staff maintain content in Desk** (done in PR 2).
3. **No competitor comparison**, anywhere.
4. **Staging first.** The pilot-user list is not used, but the control stays.
5. **Every product type gets a configurator**; question 1 routes to it; **Linear Fixture is featured** for beginners. `/portal/configure` with no category shows the same chooser.
6. **The public Webflow quiz uses live ERP data** (published products only, no prices).
7. Defaults:
   - verification −5 in scoring;
   - "Not sure" / no-preference options never filter;
   - "I'm not sure" on question 1 = Linear Fixture;
   - a dismissed banner returns when the content version changes;
   - guest sessions expire after 7 days unclaimed;
   - portal sessions expire after 30 days of inactivity;
   - results limit 60;
   - verification due date +2 business days.
8. Glossary "Learn more" HTML is sanitized on the server (`frappe.utils.sanitize_html`) in `definition.py`.

---

## 16. After deploying to staging (put this in your final message to the user)

1. Deploy `staging` and run **Migrate**. That installs the DocTypes and runs the patches: controller value maps, sessions and verification indexes, kit back-links.
2. Desk → **Catalog Configurability** → *Preview repair*, then *Apply repair*. Confirm that linear, tape, neon, sheet, kit, driver and controller products show `ok`.
3. Desk → **Product Finder Coverage**: map the remaining answers until it is empty, or until only deliberate gaps remain.
4. **Product Finder Settings:** turn on *Enable In Dealer Portal*. Check the dashboard banner, `/portal/product-finder` and the filtered catalog as a dealer test user.
5. Run the acceptance script:
   - Linear wet/IP67 → verification chip → configure → save → pending badge → request quote → staff verify → line Verified → quote can be issued;
   - driver path;
   - kit path;
   - accessories route.
6. For the public quiz: tick *Enable Public (Webflow) Quiz*, choose the staging brand, and paste the embed snippet on the staging Webflow page. Complete the quiz as a visitor, then claim it as a dealer.

---

## 17. Definition of Done (all must be true before you stop)

- [x] `staging` contains every commit on `origin/main` (already true at `579f3df`; re-merge only if `main` moved), and every check in §0.3 passes on the final commit.
- [x] §2 fixes are done (controller facets and value-map patch, `add_schedule_line` hardening, alias comment, `finder` staff capability).
- [x] A: `engine.py` matches `engine.js` (parity test); facts cover every family in the A2 table; the matcher and evaluate are implemented and cached; Desk *Preview matches* works; `prefill_for_template` covers all seven families.
- [x] B: the session DocType is extended with permissions and hooks; the sessions service and every portal endpoint are in place with validation and rate limits; the expiry scheduler is registered; the legacy wrappers are fixed.
- [x] C: the verification request DocType, line fields, service, call sites and gates, queue, conversations, notifications, schedule badges and quote-request counts are all done.
- [x] D: the React app is in portal and public modes; prototype data, recommend, resultObject, configureHandoff and CompareTable are deleted; FamilyChooser has Linear featured; both bundles are built and committed; the vitest suite passes; the CI freshness step is added.
- [x] E: the `/portal/product-finder` page, banner (dismiss and resume), nav link, "Help me choose" link, and the product-type chooser on `/portal/configure` are done.
- [x] F: the finder-scoped catalog (banner, tabs, chips, relevance, companions, empty state) and the product page (why-fits, verification callout, ask team, pairs well with, `finder` through configure and save, "Back to your matches") are done.
- [x] G: driver, controller and kit configurators work end to end (projection, `kit_template`, configure page branches, JS classes, server-validated saves, Desk kit dialog on the shared writer, kit route redirect).
- [x] H: the public API (published-only, no prices), CORS, the claim flow, the public bundle and embed docs are done; the prototype Vercel preview is retired.
- [x] §12 hardening is done; §13 tests are all written and passing; §14 docs are updated.
- [x] Everything is pushed to `staging`. The final message to the user summarizes what was built, the verification results, the defaults chosen, and the §16 steps.
