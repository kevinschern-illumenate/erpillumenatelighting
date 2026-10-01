# Product Finder in the Dealer Portal — Implementation Plan

Status: proposed, 2026-10-01. Target branch: `staging`.

## 1. Goal

Bring the guided quiz in `tools/configurator_ui` into the Dealer Portal, alongside the existing `/portal/configure` configurator. The quiz is for customers who know little about lighting. It uses pictures, tooltips and "Learn more" text.

Target flow:

1. A dealer signs in to `/portal`. A small banner advertises the **Product Finder**.
2. The banner opens the quiz at `/portal/product-finder`.
3. When the quiz is finished, the dealer lands on `/portal/products`. The catalog shows **only the products that fit their answers**, ranked by fit, with the reasons each one matches.
4. From a product page they either:
   - **configure** a linear fixture, tape, neon or sheet and save it to a project's fixture schedule, or
   - **add** an accessory, driver, controller, kit or component to a fixture schedule as a line.

The plan also fixes the product catalog. That includes the reason the configurator does not appear on product pages even though fixture templates exist (§3). Those fixes are Phase 0 and can ship before any Product Finder work.

---

## 2. What exists today

### 2.1 The quiz prototype (`tools/configurator_ui`)

- A Vite + React 18 + Tailwind 3 app. `npm run build` produces an IIFE bundle for Webflow (`window.IllConfigurator.mount`). `npm run build:preview` produces a standalone SPA in `dist-preview/`, which is used on Vercel.
- `src/content/questions.json` defines 17 questions with branching (`visibleWhen`, `skipWhen`, option-level `hideWhen`). Six are currently hidden with an empty `skipWhen.all`, which evaluates to true: `target_cct`, `run_length`, `continuous_run`, `power_injection`, `supply_voltage` (hard-coded to 24 VDC) and `operating_temp`.
  The questions a user actually sees are: indoor/outdoor → moisture → IP rating (damp/wet only) → light type → color mode (full color only) → fixture purpose → installation method → CCT range (tunable only) → CRI → dimming protocol → diffuser → finish.
- `src/content/glossary.json` holds the tooltip and "Learn more" copy. `src/assets/*.jpg` holds 38 option images; any option without an image falls back to a color swatch.
- `src/lib/engine.js` handles visibility, answer pruning and progress. It is pure and can be reused as-is.
- `src/lib/recommend.js` does the matching. Hard filters: environment rating (meets or exceeds), IP rating (meets or exceeds), light type, color mode, dimming protocol, voltage and mounting method. Soft checks: CRI, CCT and the lumens/ft band, relaxed in that order when nothing matches.
- **Data is entirely offline.** `src/data/products.seed.json` contains 151 records, all of them **LED Tape**. It has no linear fixtures, neon, sheets or accessories. `competitors.sample.json` is illustrative only.
- `src/lib/configureHandoff.js`: "Configure Now" sends the top recommendation to `/portal/configure?category=…&template=…&moisture=…`. It also calls `configurator_session.save_session`, using a CSRF token from a `csrftoken` cookie that Frappe does not set.
- The results screen shows a JSON download/copy/console panel, a competitor table, and a footer reading "Prototype using seeded offline data". None of these belong in the portal.

### 2.2 Portal pieces this builds on

| Piece | Location | Notes |
|---|---|---|
| Portal home | `templates/pages/portal.html`, `portal.py` | `can_view_catalog` already gates a "Product Catalog" card. This is where the banner goes. |
| Portal nav | `templates/includes/portal_navigation.html` | Has only Overview, Projects, Support and Account. There is **no Products link**. |
| Catalog page | `templates/pages/products_catalog.{py,html}`, `public/js/product_catalog.js` | URL-driven filters, facet sidebar, paging. |
| Catalog API | `api/product_catalog.py` | `get_catalog_products`, `get_catalog_product_detail`, `get_catalog_filter_options`. |
| Product projection | `api/product_projection.py::project_product` | Decides `capability` (`configure` / `quantity` / `inquiry` / `unavailable`) and `configure_url`. |
| Product page | `templates/pages/product_detail.{py,html}`, `public/js/product_detail.js` | Has an "Add to a Fixture Schedule" panel. Configurable products open the configurator with a line draft; others become accessory lines through `portal/standard_products.py`. |
| Configurator | `templates/pages/configure.py` and `public/js/configurator/*` | Already accepts `quiz_handoff` query parameters (`moisture`, `cct`, `lens`…) and pre-fills from them (`shared_configurator.js:40`). |
| Quiz session | DocType `ilL-Configurator-Session`, `api/configurator_session.py` | Fields: `user`, `session_token`, `product_type` (Linear/Tape/Neon), `recommended_template`, `quiz_answers`, `status`. Only System Manager has permissions. |
| Rollout gate | `portal/rollout.py::available` | Site config keys `ill_portal_enabled_families` and `ill_portal_pilot_users`. |

---

## 3. Why the configurator does not appear on product pages

`product_detail.js` shows the configurator only when the API returns a `configure_url`. `project_product` builds that URL only when **all** of these hold: the product is active, its template link is set, `is_configurable` is checked, there are **no `validation_errors` in `configurator_options`**, and the rollout gate passes. If any one fails, the page shows *"This product is not yet orderable from the portal. Contact us…"* and links to support.

### 3.1 Root cause (confirmed): linear fixtures are always downgraded to "inquiry"

- `ilL-Webflow-Product.populate_configurator_options()` runs on every save of a configurable linear fixture. It writes step 4 (*Output Level*) from `_get_output_levels_lens_map()`, which returns a **dict**: `{"lensMap": {...}}` (`ill_webflow_product.py:2975`).
- `project_product` requires every row's `allowed_values_json` to be a list. Anything else raises `ValueError("Allowed values must be an array of choices")` (`product_projection.py:59`). The row is recorded as `INVALID_OPTIONS`, and `capability` falls back to `"inquiry"` (`product_projection.py:76-79`).
- The step-4 row is written whenever the template has tape offerings with output levels. In practice that means **every configurable linear fixture product projects as inquiry-only**, and no product page shows the configurator for it.

I reproduced this against the real function:

```text
plain options row   -> capability: configure
with the lensMap row -> capability: inquiry, validation_errors: [{code: INVALID_OPTIONS, step: 4}], configure_url: None
```

The existing contract test (`tests/portal_unit/test_contracts.py`) only uses list-shaped options, so it never caught this. The same projection feeds the catalog cards, the product page, readiness checks and spec downloads, so the downgrade shows up everywhere.

### 3.2 Other gates that can also hide the configurator (check each on the live site)

1. **Pilot list.** If site config `ill_portal_pilot_users` is set, every dealer who is not in that list (and is not sales or engineering staff) gets `configure_available=False`, which means inquiry for every family. Likewise, `ill_portal_enabled_families` hides any family it does not name.
2. **`is_configurable` defaults to 0** on `ilL-Webflow-Product`. Products created by hand in Desk (as opposed to `tools/fixture_builder`, which sets it to 1) are inquiry-only until someone ticks the box.
3. **Missing template link.** `capability` requires `fixture_template` (when the product type is "Fixture Template"), `tape_neon_template` (tape/neon) or `led_sheet_template`. Fixture templates "existing in the system" is not enough: the Webflow product must link to them.
4. **Inactive template.** The projection never checks the template's `is_active`. `configure.py` lists only active templates, so the page can link to a configurator that then has no matching template to select.
5. **Families with no configurator path.** `TEMPLATE_FIELDS` covers only Linear, Tape, Neon and Sheet. Drivers, controllers and extrusion kits are never configurable from the catalog, even though `driver_controller_configurator.py` and `extrusion_kit_configurator.py` exist. The `/portal/configure-kit` routes in `hooks.py:110-111` point to a page, `configure_kit`, **that does not exist**, so they return 404.

---

## 4. Target architecture (decisions)

| Decision | Recommendation | Why |
|---|---|---|
| Where matching runs | **Server-side Python is the source of truth** (`portal/product_finder.py`). The React UI calls it for live option counts and final results. | Catalog filtering and quiz results must agree. Live ERP data cannot be shipped to the browser as a seed file. Python avoids a second copy of the logic in JS. |
| Product data | Built from live `ilL-Webflow-Product` records: attribute links plus the linked templates. Cached and invalidated on save. | Replaces the tape-only offline seed. Covers linear, tape, neon and sheet. |
| Answer → ERP value mapping | A versioned JSON file, `illumenate_lighting/config/product_finder/mapping.json`, plus a Desk coverage report (§6.6). | Reviewable in PRs and testable. A Desk-editable DocType is a possible later step (see §12). |
| Questions and glossary | Move `questions.json` and `glossary.json` to `illumenate_lighting/config/product_finder/`. The Vite app imports them from there; Python reads the same files. | One source of truth for branching and validation on both sides. |
| UI | Reuse the React app in a new **portal mode**. Build it as an IIFE and commit the output under `illumenate_lighting/public/product_finder/`. | Frappe Cloud runs `bench build` (esbuild) but does not run Vite or Tailwind. Committing the build output is how this app can ship. CI checks that the output is fresh. |
| Quiz state | Extend `ilL-Configurator-Session`: autosave answers, store results, restrict access to the owner. | Supports resume, "Edit answers", and catalog URLs that do not carry answers in the query string. |
| Catalog integration | `/portal/products?finder=<token>`. The catalog API restricts to the session's matched products and orders them by score. | Keeps the existing catalog UI and its filters. Dealers can refine further or clear the finder. |
| Feature flag | Site config `ill_portal_product_finder` (read with `conf_flag`). | Allows a staged rollout, the same way `ill_portal_fixture_groups` works. |

---

## 5. Phase 0 — Product catalog fixes (ship first, independent)

Each item lists the change, the files, and the tests.

### C1. Accept metadata-shaped configurator options *(fixes §3.1)*

- `api/product_projection.py`: let `allowed_values_json` be either a list of `str`/`dict` **or** a dict object (metadata such as `{"lensMap": …}`). Keep rejecting malformed JSON, scalars and lists of numbers.
  - Mark metadata rows (dict-valued, or `option_step >= 90` such as 98 and 99) with `"metadata": true` in the projected `configurator_options`, so consumers do not render them as choices.
  - **Do not** change the stored shape in `ill_webflow_product.py`. Webflow's part-number builder reads `lensMap` from the CMS.
- Tests (`tests/portal_unit/test_contracts.py`):
  - The real step-4 shape (`{"lensMap": {"WH": [...]}}`) projects as `configure` with a `configure_url`.
  - Steps 98 and 99 (lists of dicts) project as configure.
  - `"broken"`, `5` and `[1, 2]` still produce `INVALID_OPTIONS`.
- Installed-site regression: save a Webflow product linked to a seeded fixture template with tape offerings. Assert `get_catalog_product_detail` returns `capability == "configure"`.

### C2. Explain why a product is not configurable

- Add `capability_reason` to the projection: `inactive`, `not_configurable`, `missing_template`, `inactive_template`, `invalid_options:<step>`, `family_not_enabled`, or `pilot_only`. `rollout.available` must return the reason as well as the boolean, so add a `rollout.reason(family)` helper.
- In `product_detail.js`, inquiry mode: dealers still see the friendly message. Staff (`frappe.boot`/context flag `is_staff`) also see the reason and a link to the Desk record (`/app/ill-webflow-product/<name>`).
- Tests: one unit test per reason, and a DOM test that staff see the reason and dealers do not.

### C3. Check that the linked template is active

- In `get_catalog_products` and `get_catalog_product_detail`, fetch the `is_active` flag of the linked templates (one batched `frappe.get_all` per template DocType) and pass `template_active` into `project_product`. An inactive template gives `capability_reason = inactive_template`.

### C4. Data repair and a coverage report

- New Desk report **"Catalog Configurability"** (Script Report under `illumenate_lighting/report/`). It lists every active Webflow product with family, template link, template active flag, `is_configurable`, capability and `capability_reason`.
- One-off, idempotent patch `patches/link_configurable_catalog_products.py`. For each active `ilL-Fixture-Template`, `ilL-Tape-Neon-Template` and `ilL-LED-Sheet-Template` whose `webflow_product` back-link points at a product, make sure that product has the matching template field set and `is_configurable = 1`, then save it so `before_save` regenerates its options. The patch should **log** what it changes and skip inactive products. Have staff review a dry run (a bench execute function with `dry_run=1`) before the patch is registered.
- Runbook: check `bench --site <site> show-config` (or Frappe Cloud → Site Config) for `ill_portal_pilot_users` and `ill_portal_enabled_families`. Remove them, or add every dealer family, before launch.

### C5. Numeric filter values break filtering

- `product_catalog.js:146-147` reads filter values with jQuery `.data('val')`. jQuery converts numeric-looking strings such as `"90"` (CRI) or `"24"` into numbers. The API then rejects the filters ("Choose up to 20 filters…") and the grid shows "Products unavailable".
- Fix: use `this.getAttribute('data-val')` / `data-attr`, and the same for `data-type` on the product-type tabs.
- DOM test: tick a facet whose value is `"90"`. The request should send `["90"]` as a string.

### C6. Unknown query parameters become attribute filters

- `readUrlState` (`product_catalog.js:43`) treats every parameter except `q`, `type` and `page` as an attribute filter. `?utm_source=…`, `?finder=…` and `?schedule=…` all turn into filters that match nothing.
- Fix: accept only attribute types that exist in `get_catalog_filter_options` (apply them after the filter metadata loads), plus `series` and `product_category`. Reserve `finder`, `schedule`, `line_key` and `line_idx` as context parameters that are carried through to product links.
- DOM test: `?utm_source=x&CCT=3000K` sends only the CCT filter.

### C7. Facet counts ignore the current filters

- `get_catalog_filter_options` returns global counts, so a dealer can tick a value that has a count but produces zero results.
- Fix: accept the same `filters`, `search` and `finder` arguments and compute disjunctive facets: counts for each group apply every *other* active group. Hide options with zero count unless they are selected.

### C8. Labels and calls to action dealers can act on

- Product-type tabs and badges show the raw value "Fixture Template". Map it to **"Linear Fixtures"** for display (keep the value). Use the same label map on cards and the product page.
- Catalog cards: configurable products get a **"Configure"** primary button linking to `/portal/products/<slug>#configure`, which scrolls to and focuses the action panel. Others get **"Add to schedule"**. Both keep "View details".

### C9. Guests and non-dealers get an error page

- `products_catalog.py` and `product_detail.py` call `frappe.throw` for Guest users. Copy the redirect pattern from `configure.py`: send guests to `/login?redirect-to=<current url>`, and send users without catalog access to `/portal/request-dealer-access`.

### C10. Navigation

- Add **Products** to `portal_navigation.html` (shown when `can_view_catalog`). When the flag is on, also add **Product Finder**.

### C11. Product page with no schedule to add to

- When `standard_products.prepare` returns no editable schedules, the form becomes a dead end ("No editable schedules found").
- Add a **"New project / schedule"** inline flow using the existing `api.portal.create_project` and `api.portal.create_schedule`, then select the new schedule.
- Remember the last schedule used (`localStorage` key `ill-last-schedule`, wrapped in try/catch) and preselect it.

### C12. Dead `/portal/configure-kit` routes

- Remove both rules from `hooks.py` (kits are added as accessory lines today), **or** build the page around `extrusion_kit_configurator.py`. Recommendation: remove them now and track a kit configurator separately.

### C13. Quiz handoff pre-fill uses labels where codes are expected

- `shared_configurator.js:40-46` maps handoff values such as `moisture=Damp` or `cct=3000K` onto `environment_rating_code` and `cct_code`. The configurator's selects use **attribute codes**, so the pre-fill most likely does nothing. Confirm this in the browser.
- Fix as part of §9: resolve answers to template-valid codes **on the server** (`product_finder.prefill_for_template`) and pass them in `initial_request.selections`. Keep accepting the raw parameters for old Webflow links.

### C14. Small robustness items

- Product page: `window.crypto.randomUUID` needs a secure context. Fall back to `frappe.utils.get_random(16)` when it is missing.
- Catalog: add `aria-live` result-count updates, and give the active filter chips a removable "x".

---

## 6. Phase 1 — Product Finder backend

### 6.1 Module layout

```
illumenate_lighting/config/product_finder/
    questions.json        # moved from tools/configurator_ui/src/content/
    glossary.json         # moved from tools/configurator_ui/src/content/
    mapping.json          # NEW: answer value -> ERP attribute values / rules
illumenate_lighting/illumenate_lighting/portal/product_finder.py   # pure engine
illumenate_lighting/illumenate_lighting/api/product_finder.py      # whitelisted endpoints
```

### 6.2 `mapping.json`: answers to ERP data

One entry per question. Each entry names the facet it reads from a product and how to compare:

```jsonc
{
  "version": 1,
  "families": ["Linear Fixture", "LED Tape", "LED Neon", "LED Sheet"],
  "questions": {
    "moisture":   {"facet": "environment_rating", "mode": "hard", "compare": "rank_gte",
                    "rank": {"Dry": 0, "Damp": 1, "Wet": 2},
                    "erp": {"Dry": ["Dry"], "Damp": ["Damp"], "Wet": ["Wet"]}},
    "ip_rating":  {"facet": "ip_rating", "mode": "hard", "compare": "rank_gte",
                    "rank": {"IP65": 0, "IP67": 1, "IP68": 2}, "unknown": "include_with_warning"},
    "light_type": {"facet": "light_type", "mode": "hard", "compare": "in",
                    "derive_from": {"LED Package": {"Static White": "Static white", "Full Spectrum": "Static white",
                                                      "Tunable White": "Tunable white", "Dim to Warm": "Dim-to-warm",
                                                      "RGB": "Full-color", "RGBW": "Full-color", "Pixel": "Full-color"}}},
    "installation_method": {"facet": "mounting_method", "mode": "hard", "compare": "any",
                    "erp": {"Surface": ["Surface"], "Recessed": ["Recessed"], "Angled": ["Angled", "Corner"],
                            "Drywall-plaster-in": ["Plaster-In", "Trimless"], "Suspended": ["Suspended", "Pendant"]}},
    "dimming_protocol": {"facet": "dimming_protocol", "mode": "hard", "compare": "any"},
    "cri":        {"facet": "cri_min", "mode": "soft", "compare": "gte", "erp": {"90+": 90, "95+": 95}},
    "fixture_purpose": {"facet": "lumens_per_ft", "mode": "soft", "compare": "band", "bands": "lumensBands"},
    "diffuser":   {"facet": "lens_appearance", "mode": "soft", "compare": "any",
                    "erp": {"Clear": ["Clear"], "Frosted": ["Frosted"], "White": ["White"], "Black": ["Black"]}},
    "finish":     {"facet": "finish", "mode": "soft", "compare": "any",
                    "erp": {"Silver": ["Anodized Silver", "Silver"], "Black": ["Black"], "White": ["White"]}}
  }
}
```

The ERP strings above are **placeholders**. Fill them in from the real `ilL-Attribute-*` names using the coverage report (§6.6) before launch. A unit test fails if any mapped ERP value is not in the attribute fixtures/seed used by the test site.

### 6.3 Product facts (`product_finder.product_facts()`)

For each active `ilL-Webflow-Product` in the finder families, build one dict:
`name, slug, family, template, capability, environment_rating[], ip_rating, light_type[], color_modes[], dimming_protocol[], mounting_method[], lens_appearance[], finish[], cri_min, cct_available[], cct_tunable_min/max, lumens_per_ft[] (delivered), input_voltage, product_category`.

Sources, in order of preference:
1. `attribute_links` (Environment Rating, LED Package, CCT, CRI, Dimming Protocol, Mounting Method, Lens Appearance, Output Level, Output Voltage). These are already populated by `populate_attribute_links()`.
2. The linked template, for anything attribute links do not carry: allowed options, tape offerings, and the IP rating for neon.
3. Numeric values from the attribute masters: `ilL-Attribute-Output Level.value` and the CRI minimum.

**Cache:** `frappe.cache().get_value("ill_product_finder_facts")`. Clear it in `doc_events` `on_update`/`on_trash` for `ilL-Webflow-Product`, the three template DocTypes and the attribute masters that already have `on_attribute_update` hooks (`hooks.py:331-351`). Also set a 1-hour TTL as a backstop.

Only products with `capability in ("configure", "quantity")` for the **current user** are eligible. The final filter runs per request, so the rollout gate still applies.

### 6.4 Matching (`product_finder.match(answers)`)

Port the semantics of `recommend.js`, driven by `mapping.json`:

1. `prune_hidden_answers(answers)`: same rules as `engine.js`, evaluated against the shared `questions.json`.
2. Hard filters. Products whose facet is **unknown** follow the question's `unknown` policy: `exclude` (the default) or `include_with_warning`. This avoids silently hiding products whose IP data is missing.
3. Soft checks and scoring: CRI, CCT, lumen band, diffuser and finish. Relax CRI, then CCT, then lumens when nothing passes. Return `relaxed` labels.
4. Output: `{matches: [{name, score, reasons[], tradeoffs[]}], relaxed[], no_hard_match, counts_by_family}`.
5. **Companions** (the "add accessory or other product" part of the request):
   - drivers whose `Dimming Protocol` and `Output Voltage` facets match the answers,
   - controllers for the chosen protocol (DMX/SPI/DALI),
   - every `compatible_products` row of the top matches.
   Return them as `companions: [{name, relation}]`. They are not scored.

`evaluate(answers, next_question_id)` returns `{match_count, option_counts: {value: n}, disabled: [values]}` for the question being answered. The UI uses it to show "12 products" on each option card and to grey out options that would eliminate everything. This replaces `optionWouldEliminateAll`, which ran against the offline seed.

### 6.5 Session model: extend `ilL-Configurator-Session`

| Field | Type | Purpose |
|---|---|---|
| `product_type` | Select | Make it optional and add `Mixed` (the finder spans families). |
| `source` | Select `Portal` / `Webflow` | Analytics, and to keep the old Webflow handoff working. |
| `questions_version` | Data | The version of `questions.json` the answers were given against. |
| `quiz_answers` | JSON (was Long Text) | Answers, validated and size-capped (16 KB). |
| `result_json` | JSON | The `match()` output saved at completion: names, scores, reasons, relaxed. |
| `result_computed_at` | Datetime | Recompute if older than the facts cache. |
| `completed_on` | Datetime | |
| `status` | Select | `Active` → `Completed` → `Used` (configured or added to a schedule) / `Expired`. |

- **Permissions:** add `Dealer` and the internal portal roles with read/write on records they own (`if_owner`), plus `permission_query_conditions` and a `has_permission` hook limiting reads to `user == session user` (System Manager and sales staff excepted). Every API call resolves the session by token **and** owner.
- **Expiry:** a daily scheduler job marks sessions untouched for 30 days as `Expired`.
- Fix `api/configurator_session.save_session`: reject Guest, validate `quiz_answers` as JSON within the size limit, and stop the explicit `frappe.db.commit()` (let the request commit).

### 6.6 Desk report: "Product Finder Coverage"

For each active product in the finder families: which facets are populated, which ERP values have no entry in `mapping.json`, which `LED Package` values cannot be mapped to a light type, and capability plus reason (shared with C4). This is the go-live checklist for data.

### 6.7 Whitelisted endpoints (`api/product_finder.py`)

All of them require login, `require_catalog_access()` and `conf_flag("ill_portal_product_finder")`.

| Method | Verb | Purpose |
|---|---|---|
| `get_definition()` | GET | Questions, glossary, lumen bands and `questions_version`, so the bundle and server cannot drift. |
| `start()` | POST | Creates a session and returns its `token`. |
| `get_session(token)` | GET | Answers and status, for resume and "Edit answers". |
| `save_answers(token, answers)` | POST | Debounced autosave from the UI. Validates against the schema. |
| `evaluate(answers, question_id)` | POST | Live option counts (§6.4). Rate-limited with `frappe.rate_limiter` at 120/min per user. |
| `complete(token)` | POST | Runs `match`, stores `result_json`, sets `Completed`, returns `{catalog_url}`. |
| `dismiss_banner()` | POST | Stores the user default `ill_finder_banner_dismissed=1`. |

Validation rejects unknown question IDs, option values not in the question's options, numbers outside min/max, and ranges where low > high.

---

## 7. Phase 2 — Finder UI in the portal

### 7.1 Page

- Route in `hooks.py`: `{"from_route": "/portal/product-finder", "to_route": "product_finder"}`.
- `templates/pages/product_finder.py`:
  - Guest → login redirect.
  - No catalog access → `/portal/request-dealer-access`.
  - Flag off → redirect to `/portal/products`.
  - Context: `session_token` (from `?session=` if the user owns it, otherwise none) and the `csrf_token`.
- `product_finder.html` extends `templates/web.html`, includes `portal_navigation.html`, and renders `<div id="ill-configurator-root" data-ill-manual-mount></div>`. It loads `/assets/illumenate_lighting/product_finder/ill-configurator.{css,js}` and calls:

```js
window.IllConfigurator.mount('ill-configurator-root', {
  mode: 'portal', sessionToken: {{ session_token|tojson }},
  csrfToken: frappe.csrf_token, catalogUrl: '/portal/products'
});
```

### 7.2 React changes (`tools/configurator_ui`)

1. **Config plumbing.** `App` already receives `config`. Pass it to `Wizard` and `Results` through a small `ConfigContext`.
2. **Data source by mode.** Add `src/lib/api.js` with `start`, `getSession`, `saveAnswers`, `evaluate` and `complete`. It uses `fetch` with `X-Frappe-CSRF-Token: config.csrfToken` and same-origin credentials.
   - In `portal` mode, `QuestionStep` takes option counts and disabled state from `evaluate()` (debounced 150 ms; show the last counts while loading).
   - In `webflow` mode, the existing seed logic stays unchanged until Webflow moves over (§10).
3. **Shared content.** Change the imports to `../../../../illumenate_lighting/config/product_finder/questions.json` and add `server.fs.allow` in `vite.config.js`. Delete the copies in `src/content/`.
4. **Autosave and resume.** Debounce `saveAnswers` by 500 ms. On mount with `sessionToken`, load the answers. "Start over" calls `start()` again.
5. **Portal results screen.** Replace the results panel in portal mode with:
   - "We found **N** products that fit your project", with counts per family.
   - The relaxation notice, if any.
   - A preview of the top three matches (image, name, "why it fits").
   - Primary CTA **"See matching products"** → `complete()` → navigate to `catalog_url`.
   - Secondary actions: "Edit answers" and "Start over".
   - **Removed** in portal mode: JSON download/copy/console, the competitor table, and the "Prototype…" footer.
6. **Content tweaks for non-experts:**
   - "Outdoor" hides the "Dry" moisture option (`hideWhen`).
   - Add a first optional question, **"Where is this light going?"** (cove, under-cabinet, display case, signage, façade, landscape). It maps to `product_category` (Application), which the catalog already facets on.
   - Add the missing `target-cct-*.jpg` images, or keep the swatches.
   - Re-check glossary copy for every visible question.
7. **Accessibility and mobile:**
   - Option cards become buttons with `aria-pressed`.
   - Move focus to each newly revealed question's heading.
   - Respect `prefers-reduced-motion` for `scrollIntoView`.
   - Make sure the sticky SideNav does not sit under the portal navbar (`top` offset).
8. **Style isolation check.** Tailwind is scoped with `important: '#ill-configurator-root'` and preflight is disabled. Verify that Bootstrap/portal CSS (`portal.css`, `illumenate_web.bundle.scss`) does not restyle the buttons and inputs inside the root. Add scoped resets in `src/index.css` where it does.

### 7.3 Build and ship

- Add `vite.portal.config.js`: IIFE, `outDir: ../../illumenate_lighting/public/product_finder`, `base: '/assets/illumenate_lighting/product_finder/'`, and images emitted as hashed files (not inlined) to keep the JS small. Script: `"build:portal": "vite build --config vite.portal.config.js"`.
- Commit the built files. Frappe serves `public/` at `/assets/illumenate_lighting/`.
- Optimize the images to WebP at 400 px wide (about 40 KB each). The 38 JPGs are currently loaded at full size.
- CI (`.github/workflows/ci.yml`): new job running `npm ci && npm run build:portal && git diff --exit-code illumenate_lighting/public/product_finder`, so a stale bundle fails the PR.
- `tools/check_portal_templates.py`: add the new template to its parse and embedded-script checks.

---

## 8. Phase 3 — Dashboard banner and entry points

- In `portal.py`, add to the context:
  - `finder_enabled = conf_flag("ill_portal_product_finder") and can_view_catalog`
  - `finder_banner_dismissed = frappe.defaults.get_user_default("ill_finder_banner_dismissed")`
  - `finder_resume`: the user's latest `Active` session, if there is one.
- In `portal.html`, between the hero and the card row:
  - A slim, dismissible banner (about 96 px tall on desktop; it stacks on mobile).
  - Contents: a thumbnail (`fixture-purpose-ambient.webp`), the headline **"Not sure which fixture fits your project?"**, the sub-line *"Answer a few picture-guided questions and we'll show you the products that fit."*, the CTA **"Start the Product Finder"** (or **"Resume"** with a progress hint when `finder_resume`), and a close "x".
  - The close button calls `dismiss_banner()` and hides the banner without a reload. A dismissed banner reappears only when an admin resets the default; "Product Finder" stays in the nav and on the catalog.
- Other entry points:
  - A **"Help me choose"** link in the catalog header.
  - A Product Finder card on the portal home when the banner is dismissed.
  - A nav link (C10).

---

## 9. Phase 4 — Catalog filtered by the quiz

### 9.1 API

`get_catalog_products(..., finder=None, sort=...)`:
- If `finder` is set: load the session by token with an owner check. If `result_json` is stale, recompute `match()`.
- Add the condition `` `tabilL-Webflow-Product`.name IN %(finder_names)s ``.
- Add a `relevance` sort that orders by score. Use a `CASE` built from the parameterized name list; with an active finder it is the default.
- Attach `match: {score, reasons, tradeoffs, best}` to each projected product.
- Return a top-level `finder` block: `{token, answers_summary: [{question, label}], relaxed, total_matches, companions_count}`.
- Normal attribute and search filters still narrow within the finder set.
- `view=companions` returns the session's companion products (drivers, controllers, accessories) instead.

`get_catalog_filter_options(finder=…)` scopes facet counts to the finder set (it builds on C7).

### 9.2 UI (`products_catalog.html` and `product_catalog.js`)

- `CatalogState.finder` comes from `?finder=`, a reserved parameter (C6).
- A **finder banner** above the grid:
  - "Showing **N** products that match your answers."
  - Answer chips (Outdoor · Wet · IP67 · Static white · Surface · 0-10V …).
  - Links: **Edit answers** → `/portal/product-finder?session=<token>`, **Show all products** (drops `finder`), and **Start over**.
  - When criteria were relaxed, the banner says so.
- Tabs: **Recommended (N)** | **Drivers, controllers & accessories (M)** | **All products**.
- Cards in finder mode:
  - A "Best match" badge on the top-scored card.
  - Up to two "Why it fits" reasons and any trade-offs as small chips.
  - Every product link carries `?finder=<token>`.
- Empty finder result: explain which hard constraint eliminated everything (the API returns `no_hard_match` and the first eliminating question). Offer "Edit answers" and "Talk to us" (`/portal/support`).

---

## 10. Phase 5 — Product page, configure, add to schedule

### 10.1 Product page

- When `?finder=` is present, show a **"Why this product fits"** box above the action panel (reasons and trade-offs from `match`). Add "Back to your matches" to the breadcrumb.
- **Configure:** `configureHref` adds `finder=<token>`. `configure.py` reads it, loads the owned session and calls `product_finder.prefill_for_template(template, answers)`. That function returns only codes the template allows (environment, CCT, lens, finish, mounting, dimming). The result is passed as `initial_request = {template, selections}`, ahead of the legacy `quiz_handoff` parameters. The existing "pre-filled" banner then becomes accurate (C13).
- **Accessories and other products** (`capability == "quantity"`): the existing "Add to schedule" flow is unchanged, plus the C11 inline project/schedule creation. Pre-fill the line notes with "Added from Product Finder" so staff have context.
- **Companions:** a "Pairs well with" strip with compatible drivers, controllers and accessories, each with a quick "Add to schedule" action that reuses the standard-product flow.

### 10.2 After saving

- When a configured line saves from a finder flow, the configurator's success state adds **"Back to your matches"** (`/portal/products?finder=<token>`) next to "View schedule".
- Set the session `status = Used` on the first successful save, through a small hook in `save_configured_fixture_to_schedule` and `standard_products.add` when they receive `finder`.

---

## 11. Phase 6 — Keep the Webflow embed working

- Webflow mode stays the default for `npm run build` (`ill-configurator.js`). It keeps using the seed and `configureHandoff.js` until there is a guest endpoint.
- Fix `configureHandoff.js`: drop the nonexistent `csrftoken` cookie, and call the new `start`/`save_answers` after login.
- Better: after a Webflow user logs in, redirect them to `/portal/product-finder?import=<base64 answers>`, so the portal session takes over and they reach the filtered catalog. That removes the need for `configure.py` to understand raw quiz parameters.
- Optional later: a public `evaluate_public` endpoint (guest access, published products only, rate-limited) so Webflow can also drop the offline seed.

---

## 12. Rollout, analytics and docs

- **Flags:**
  1. Set `ill_portal_product_finder` to true on staging.
  2. Pilot it with internal staff.
  3. Turn it on for dealers.
  Phase 0 needs no flag.
- **Funnel metrics:** session counts by status (`Active` → `Completed` → `Used`), plus a simple Desk report: sessions started, completed, completion rate, top answer combinations, and zero-result rate. No third-party tracking.
- **Docs:**
  - Add a "Product Finder" section to `docs/DEALER_ROLE.md` and `docs/B2B_STAFF_OPERATIONS.md` (how to read the coverage report and fix mappings).
  - Update `tools/configurator_ui/README.md` with the portal mode, the new content location and `build:portal`.

---

## 13. Test plan

| Layer | Where | Cases |
|---|---|---|
| Python unit | `tests/portal_unit/test_contracts.py`, new `test_product_finder.py` | C1 shapes; every `capability_reason`; answer validation; hidden-answer pruning matches `engine.js` on shared fixtures; hard filters (env/IP rank, unknown policy); relaxation order; companions; session owner check; stale-result recompute. |
| DOM (node:test + jsdom) | `tests/portal_ui/catalog.test.cjs`, `standard_products.test.cjs`, new `product_finder.test.cjs` | C5 numeric values stay strings; C6 unknown parameters ignored and `finder` carried into links; finder banner chips and "Show all"; product page passes `finder` to the configure URL; banner dismiss posts and hides. |
| React | `tools/configurator_ui` (add `vitest`) | `engine.js` visibility; portal-mode results CTA calls `complete()` and navigates; the evaluate debounce. |
| Installed site | existing installed-site suite | A generated linear product projects as configure (C1 regression); `get_catalog_products(finder=…)` restricts and orders; permissions on `ilL-Configurator-Session`. |
| E2E (Playwright) | `tests/portal_e2e/portal.spec.cjs` | Dealer login → banner → finder (Outdoor/Wet/IP67/Static/Surface/0-10V) → filtered catalog → linear product → configure pre-filled → save to schedule → line visible; and the accessory → add to schedule path. |
| Lint | `ruff check .`, `ruff format .`, `tools/check_portal_templates.py` | |

---

## 14. Order of work

| # | Work | Size | Depends on |
|---|---|---|---|
| 1 | C1 lensMap fix + tests | S | — |
| 2 | C2/C3 capability reasons + template active check | S | 1 |
| 3 | C4 configurability report + dry-run repair patch; check rollout site config | M | 2 |
| 4 | C5–C10, C12, C14 catalog JS/route/nav fixes | M | — |
| 5 | C11 inline project/schedule creation | S | — |
| 6 | Move questions/glossary; `mapping.json`; facts + cache | M | — |
| 7 | Matching engine + evaluate + session model/permissions + endpoints | L | 6 |
| 8 | Coverage report; fill in the real ERP mapping values | M | 6 |
| 9 | React portal mode, build pipeline, CI freshness check | L | 7 |
| 10 | Finder page + dashboard banner + nav | S | 9 |
| 11 | Catalog finder integration (API + UI + companions tab) | M | 7 |
| 12 | Product page finder context, server prefill (C13), "Used" status | M | 11 |
| 13 | Webflow handoff cleanup | S | 12 |
| 14 | E2E, docs, staging pilot, dealer rollout | M | all |

Items 1–5 make up a standalone catalog-fix PR. Items 6–13 can follow as two or three PRs: backend, UI, then integration.

---

## 15. Open questions for the business

1. **Strictness with missing data:** if a product has no IP rating on file, should an IP67 answer hide it or show it with "confirm IP rating"? The plan defaults to hiding it, with the policy set per question.
2. **Who maintains the mapping:** engineers in `mapping.json` (reviewed in PRs), or staff in a Desk DocType? The plan starts with JSON.
3. **Competitor comparison:** drop it in the portal (recommended), or keep it for staff only?
4. **Pilot list:** is `ill_portal_pilot_users` set on production today? If so, dealers outside it see every product as "inquiry", and that alone hides the configurator for them.
5. **Kits, drivers and controllers:** should they get their own configurators from the catalog (the APIs exist), or stay "add to schedule" items?
6. **Public quiz:** should the Webflow quiz eventually use live ERP data through a guest endpoint, or keep a periodically regenerated seed?
