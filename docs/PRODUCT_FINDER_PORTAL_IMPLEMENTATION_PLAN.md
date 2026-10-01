# Product Finder and Product Catalog — Full Implementation Plan (v2)

Status: implemented in code, 2026-10-01. Branch: `staging`. Deployment and site-data acceptance remain staging operations. See [completion record](PRODUCT_FINDER_COMPLETION_PLAN.md).

> **Build status:** All implementation sections are complete: live matching and prefill, owner-bound sessions, verification and commercial gates, portal and public UI, catalog context, all seven configurator families, tests, committed bundles and operational documentation. Local verification is recorded in the completion plan; live acceptance is recorded separately.
This version replaces v1 of this document. It incorporates the decisions in §0.

---

## 0. Decisions this plan is built on

| # | Question | Decision | What it changes in the plan |
|---|---|---|---|
| 1 | A product has no data for an answer (for example, no IP rating on file) | **Show it, with a positive "needs verification" warning**: we most likely can do it, but the team must verify it before the dealer continues. | Matching adds a third result state, `verify`, alongside match and no match (§7.3). An amber warning appears on cards, product pages and schedule lines (§14.2). Staff get a verification workflow and queue (§14.3). Staff cannot issue a quote, and dealers cannot order, until the line is verified (§14.5). |
| 2 | Who maintains how quiz answers map to ERP values | **Staff, in Desk.** | Questions, options, images, help text, glossary, rules and answer→ERP mappings all live in new DocTypes (§6). The JSON files in `tools/configurator_ui` become seed data only. |
| 3 | Competitor comparison in the portal | **Dropped.** | `CompareTable` is removed from the portal and public builds (§10.3). |
| 4 | Pilot user list | **Not used. This goes to a staging site.** | Remove the pilot list from the root-cause section. Enable everything on staging with Desk toggles (§16). |
| 5 | Kits, drivers and controllers | **Give them configurators.** A question at the start routes to the right configurator. **Emphasize Linear Fixture** so a beginner can click it and get started. | The quiz's first question is a product-type chooser with Linear Fixture featured (§9.1). `/portal/configure` with no category shows the same chooser (§9.4). New portal configurators for driver, controller and extrusion kit (§13). |
| 6 | Public (Webflow) quiz data | **Live ERP data.** | Guest endpoints, rate-limited and brand-aware, with published products only (§15). The offline seed and competitor sample are retired. |

---

## 1. End-to-end journeys

### 1.1 Dealer in the portal

1. The dealer signs in and lands on `/portal`. A slim banner reads: *"Not sure which fixture fits your project? Answer a few picture-guided questions."* It has a **Start the Product Finder** button, and **Resume** if a quiz is in progress.
2. `/portal/product-finder`, **Question 1: "What are you looking for?"** Linear Fixture is a large featured card ("Most popular — not sure? Start here"). LED Tape, LED Neon, LED Sheet, Extrusion Kit, Power Supply (Driver), Controller and "Accessories & parts" are smaller cards.
3. Picture-guided questions follow for that product type. Each option shows how many products remain. Options that would leave nothing are greyed out with a reason.
4. Results summary: "We found 7 products that fit." It shows the top three, flags any relaxed criteria, and marks products needing verification with an amber chip. The CTAs are **See matching products** and **Configure the top match now**.
5. `/portal/products?finder=<token>` shows only the matching products, ranked, with "Why it fits" chips and amber "Verify with our team" chips. A second tab lists compatible drivers, controllers and accessories.
6. The product page has a "Why this fits" box and any verification warning. Its action panel either opens the family's configurator, pre-filled from the quiz, or adds a SKU to a fixture schedule (accessories). Dealers can create a project or schedule inline if they have none.
7. When the line saves to the schedule, it carries the verification flag if one applies. The schedule shows the badge. Requesting a quote is allowed and routes the line to staff. Staff verify before the quotation can be issued.

### 1.2 Public visitor on Webflow

1. The same quiz runs on Webflow against **live, published** products, with no prices.
2. Results link to Webflow product pages. **"Configure & add to a project (dealers)"** sends the visitor to log in, which claims the anonymous session into the portal (`/portal/product-finder?claim=<token>`) and opens the filtered catalog.

### 1.3 Staff

1. Desk → **Product Finder** workspace. Staff edit questions, option images and help text, glossary terms and answer→ERP mappings. The **Preview** button shows live match counts.
2. A **Coverage** report lists products with missing data and unmapped ERP values.
3. The **Product verification** queue lists requests and flagged lines. Staff mark them Verified or Not feasible and reply in the request's conversation thread.

---

## 2. Current state (summary of what was found)

- **The quiz prototype** (`tools/configurator_ui`) is a Vite + React 18 + Tailwind app.
  - `questions.json` has 17 questions; six are hidden by an empty `skipWhen.all`, which evaluates to true.
  - `glossary.json` has the help text. `src/assets` has 38 option images.
  - `engine.js` handles branching. `recommend.js` does hard and soft matching with relaxation.
  - `products.seed.json` is **offline** and holds 151 LED Tape records and nothing else. `competitors.sample.json` is illustrative only.
  - The results screen has JSON export, a competitor table and a "prototype" footer.
- **The portal** already has:
  - a catalog (`products_catalog.*`, `product_catalog.js`, `api/product_catalog.py`);
  - product pages with an "Add to a Fixture Schedule" panel (`product_detail.*`, `portal/standard_products.py`);
  - the unified configurator (`/portal/configure` with Linear, Tape, Neon and Sheet) and the unified save path `portal/configuration.save`;
  - quiz pre-fill parameters (`quiz_handoff` in `configure.py`) and an `ilL-Configurator-Session` DocType;
  - quote requests (`portal/quotes.py`), offers (`portal/offers.py`), order intake (`portal/order_intake.py`), staff queues (`portal/queues.py`) and conversations (`portal/conversations.py`).
- **Driver and controller configurator APIs** (`api/driver_controller_configurator.py`) exist as guest endpoints for Webflow. They resolve the selected options to one template variant, whose spec carries an orderable `item`. **There is no portal UI** for them.
- **The extrusion kit configurator API** (`api/extrusion_kit_configurator.py`) exists, with a **Desk-only** dialog in `ill_project_fixture_schedule.js`.
  - `save_kit_to_schedule` **trusts the client's `configuration_result`**: the part number, resolved items and kit composition all come from the client, and pricing is computed from them. It must not be exposed to dealers as it is.
  - `ilL-Webflow-Product` has **no `kit_template` field**. Only the template's `webflow_product` back-link exists.
  - The `/portal/configure-kit` routes point to a page that does not exist.

---

## 3. Why the configurator does not appear on product pages

### 3.1 Confirmed root cause

- `ilL-Webflow-Product.populate_configurator_options()` stores the linear fixture **Output Level** step as a dict, `{"lensMap": {...}}` (`ill_webflow_product.py:2975`).
- `project_product()` requires each option row to be a **list** (`product_projection.py:59`). It records `INVALID_OPTIONS` and downgrades `capability` to `inquiry` (`:76-79`), which leaves `configure_url = None`.
- `product_detail.js` therefore shows *"This product is not yet orderable from the portal"* instead of the configurator, for **every configurable linear fixture whose template has tape offerings**.
- Reproduced against the real function:

```text
list-shaped options only      -> capability: configure
plus the real step-4 lensMap  -> capability: inquiry, validation_errors [INVALID_OPTIONS step 4], configure_url None
```

### 3.2 Other conditions to check on staging (the pilot list is not one of them)

1. `is_configurable` defaults to **0** on products created by hand in Desk.
2. The product's template link field must be set (`fixture_template`, `tape_neon_template` or `led_sheet_template`). The template existing in the system is not enough.
3. The template's `is_active` is not checked by the projection, but `configure.py` lists only active templates.
4. `ill_portal_enabled_families`, if it is ever set, hides any family it does not list.

Phase 0 fixes 3.1 and adds tooling that surfaces 3.2 per product.

---

## 4. Architecture

```
            Desk (staff)                                   Portal (dealers)                 Webflow (public)
 ┌───────────────────────────────┐         ┌──────────────────────────────────────┐   ┌──────────────────────┐
 │ ilL-Product-Finder-Settings   │         │ /portal (banner)                     │   │ Webflow page          │
 │ ilL-Finder-Question (+options,│         │ /portal/product-finder  (React,      │   │ ill-configurator.js   │
 │   conditions, value maps)     │         │     portal mode)                     │   │ (React, public mode)  │
 │ ilL-Finder-Glossary-Term      │         │ /portal/products?finder=…            │   └─────────┬────────────┘
 │ Coverage / Sessions reports   │         │ /portal/products/<slug>?finder=…     │             │ guest, CORS,
 │ Verification queue            │         │ /portal/configure (chooser + 7       │             │ credentials:omit
 └──────────────┬────────────────┘         │     families)                        │             │
                │ definition + mappings    └───────────────┬──────────────────────┘             │
                ▼                                          ▼                                    ▼
      portal/product_finder/  (pure engine: definition loader, facts builder, matcher, verifier, prefill)
                ▲                                          ▲                                    ▲
   api/product_finder.py (portal, login)     api/product_catalog.py (finder-aware)   api/product_finder_public.py (guest)
                │                                          │
     ilL-Configurator-Session (answers, results)   ilL-Product-Verification-Request + schedule line flags
```

Principles:

- **One matching engine, in Python.** The portal UI, the public UI and the catalog all call it, so results never disagree.
- **Content and mappings are data, in Desk.** Engineers own the **facet registry** in code: which product facts exist and how they are read from ERP. Staff own the questions and the mappings to those facets.
- **Verification is decided on the server, never by the client.** The client cannot clear a verification flag.

---

## 5. Phase 0 — Product catalog fixes (first PR, independent)

Each fix lists the files, the change and the tests. Every fix includes its tests.

### C1. Metadata-shaped configurator options (root cause)

- `api/product_projection.py`: allow `allowed_values_json` to be a list of `str`/`dict` **or** a dict object.
  - Project dict-valued rows, and rows with `option_step >= 90`, with `"metadata": true`.
  - Malformed JSON, scalars and lists of numbers still produce `INVALID_OPTIONS`.
  - The stored shape stays the same, because Webflow reads `lensMap`.
- Tests in `tests/portal_unit/test_contracts.py`:
  - The real step-4 lensMap row → `configure` with a URL.
  - Step-98 and step-99 rows → `configure`.
  - `"broken"`, `5` and `[1,2]` → `inquiry`.
- Installed-site test: a product saved against a seeded fixture template with tape offerings → `get_catalog_product_detail().product.capability == "configure"`.

### C2. `capability_reason`

- The projection returns one of: `ok`, `inactive`, `not_configurable`, `missing_template`, `inactive_template`, `invalid_options:<step>`, `family_not_enabled`.
- Add `rollout.reason(family)`, which returns the reason as well as `available(family)`.
- `product_detail.js`: dealers see the friendly message. Staff (`is_staff` in the page context) also see the reason and a Desk link `/app/ill-webflow-product/<name>`.

### C3. Check that templates are active

- One batched `frappe.get_all` per template DocType inside `get_catalog_products` and `get_catalog_product_detail`. Pass `template_active` into `project_product`.

### C4. Configurability report and repair

- New Script Report **Catalog Configurability**: product, family, template link, template active, `is_configurable`, capability, reason.
- `bench execute illumenate_lighting.illumenate_lighting.portal.catalog_repair.link_configurable_products --kwargs "{'dry_run': 1}"`.
  - For each active template whose `webflow_product` back-link points to a product, it ensures the product's template field is set and `is_configurable = 1`.
  - It then saves the product, which regenerates its options, and prints every change.
  - Run it on staging with `dry_run=0` after staff review the dry-run output.

### C5. jQuery `.data()` turns numeric labels into numbers

- `product_catalog.js:146-147`: use `getAttribute('data-attr' | 'data-val' | 'data-type')`.
- DOM test: a facet value `"90"` is sent as the string `["90"]`.

### C6. Unknown query parameters become filters

- `readUrlState()` accepts only attribute types present in the filter metadata, plus `series` and `product_category`.
- Reserved context parameters `finder`, `schedule`, `line_key`, `line_idx` and `draft` are carried into product links instead.
- DOM test: `?utm_source=x&CCT=3000K` sends only CCT.

### C7. Context-aware facet counts

- `get_catalog_filter_options(filters, search, finder)` computes disjunctive counts: each group applies every *other* active group.
- Hide options with zero count unless they are selected.

### C8. Labels and calls to action

- Display "Fixture Template" as **Linear Fixtures**, and use family labels everywhere.
- Cards for configurable products get a **Configure** button (`/portal/products/<slug>#configure`, which focuses the action panel). Quantity products get **Add to schedule**. All keep **View details**.

### C9. Guest and non-dealer handling

- `products_catalog.py` and `product_detail.py`: send guests to `/login?redirect-to=…` and users without catalog access to `/portal/request-dealer-access`, the same as `configure.py`.

### C10. Navigation

- `portal_navigation.html`: add **Products** when `can_view_catalog`, and **Product Finder** when Settings has `portal_enabled` on.

### C11. Product page with no schedule

- Inline **New project / schedule** using `api.portal.create_project` and `create_schedule`, which then selects the new schedule.
- Remember the last schedule used in `localStorage` (`ill-last-schedule`, inside try/catch).

### C12. Dead kit routes

- Replace the `/portal/configure-kit` rules with a redirect to `/portal/configure?category=Extrusion%20Kit`, which exists after §13.

### C13. Quiz pre-fill uses labels where codes are expected

- `shared_configurator.js:40-46` maps label values (`moisture=Damp`) onto `*_code` fields, so the pre-fill most likely does nothing.
- Replaced by the server-side `prefill_for_template()` in §12.3. Legacy parameters are converted on the server too.

### C14. Robustness

- Fall back to `frappe.utils.get_random(16)` when `crypto.randomUUID` is missing.
- Catalog result counts get `aria-live`.
- Active filter chips become removable.

### C15. Kit save trusts the client (security, required before §13)

- `extrusion_kit_configurator.save_kit_to_schedule` must stop trusting `configuration_result`.
- New service `portal/kit_configuration.save(schedule_name, selections, idempotency_key, expected_modified, line_key=None, metadata=None, finder=None)`:
  - Re-runs `validate_kit_configuration(selections)` on the server.
  - Computes pricing on the server.
  - Uses `schedule_context(write=True, lock=True)`, the same receipt and idempotency pattern as `portal/configuration.save`, and catalog access checks.
- The old endpoint stays for the Desk dialog but re-validates the same way.

---

## 6. Phase 1 — Finder content managed in Desk

### 6.1 DocTypes

All of them go in module **Illumenate Lighting**. Permissions: **System Manager** and a new role **ilL Product Finder Manager** get full access. Sales and engineering staff can read.

#### `ilL-Product-Finder-Settings` (Single)

| Field | Type | Notes |
|---|---|---|
| `portal_enabled` | Check | Turns on the portal finder, the banner and the nav link. |
| `public_enabled` | Check | Turns on the guest endpoints for Webflow. |
| `public_brands` | Table MultiSelect → `ilL-Child-Webflow-Brand-Target` | Which brands may call the public API. |
| `banner_enabled` | Check | |
| `banner_headline` | Data | Default: "Not sure which fixture fits your project?" |
| `banner_text` | Small Text | Default: "Answer a few picture-guided questions and we'll show you the products that fit." |
| `banner_image` | Attach Image | |
| `banner_cta_label` | Data | Default: "Start the Product Finder" |
| `verification_title` | Data | Default: "Most likely a fit — our team will confirm" |
| `verification_text` | Small Text | Default copy in §14.2. Supports `{reasons}`. |
| `default_unknown_policy` | Select: Verify / Exclude / Include silently | Default **Verify** (decision 1). |
| `verification_gate` | Select: Before quote is issued and order is placed / Before order only / Warning only | Default: the first option. |
| `verification_assignee_role` | Link Role | Who gets the queue. Default: the sales capability. |
| `results_limit` | Int | Default 60. |
| `session_expiry_days` | Int | Default 30. Guest sessions expire after 7 days. |
| `definition_version` | Int, read-only | Bumped on any content change. Used for caches and session staleness. |

#### `ilL-Finder-Question` (one record per question; name `field:question_key`)

| Field | Type | Notes |
|---|---|---|
| `question_key` | Data, unique | For example `moisture`. Must be a valid identifier. |
| `is_active` | Check | |
| `sequence` | Int | Order in the quiz. |
| `families` | Table → `ilL-Child-Finder-Family` (`family` Select: Any, Linear Fixture, LED Tape, LED Neon, LED Sheet, Extrusion Kit, Driver, Controller). A plain grid, because Table MultiSelect needs a Link field. | Which product-type paths ask this question. |
| `short_label` | Data | Side-nav label. |
| `label` | Data | The question text. |
| `tooltip` | Small Text | Always-visible short help. |
| `learn_more` | Text Editor | Expandable long help. |
| `glossary_term` | Link `ilL-Finder-Glossary-Term` | Optional shared term. |
| `question_type` | Select: Family chooser / Single / Multi / Number / Range / Info | |
| `required` | Check | |
| `number_min`, `number_max`, `number_step`, `unit`, `placeholder`, `range_default_low`, `range_default_high` | Float/Data | For Number and Range questions. |
| `facet` | Select (registry, §7.1) | The product fact this question tests. Empty means display only. |
| `match_mode` | Select: Hard / Soft / Rank only / None | |
| `comparison` | Select: Any of / Meets or exceeds (rank) / At least (number) / Within band (number) / Range covers | |
| `unknown_policy` | Select: Use default / Verify / Exclude / Include silently | |
| `relax_priority` | Int | Soft questions only. Lower numbers are relaxed first (CRI 10, CCT 20, lumens 30). |
| `verification_reason_template` | Data | For example "IP rating {answer} on this product". |
| `options` | Table → `ilL-Child-Finder-Option` | |
| `conditions` | Table → `ilL-Child-Finder-Condition` | |
| `value_maps` | Table → `ilL-Child-Finder-Value-Map` | Answer → ERP mapping. |

`ilL-Child-Finder-Option`

| Field | Type | Notes |
|---|---|---|
| `value` | Data | Stored answer value. Unique per question. |
| `label` | Data | |
| `description` | Small Text | One line under the label, for beginners. |
| `image` | Attach Image | Option picture. Falls back to `swatch_color`. |
| `swatch_color` | Data | Hex value or CSS gradient (validated). |
| `glossary_term` | Link | |
| `note` | Data | For example "Limited availability". |
| `is_featured` | Check | Rendered as the large card (Linear Fixture). |
| `badge_text` | Data | For example "Most popular — not sure? Start here". |
| `rank` | Int | For meets-or-exceeds comparisons (Dry 0 / Damp 1 / Wet 2; IP65 0 / IP67 1 / IP68 2). |
| `numeric_min`, `numeric_max` | Float | Lumen bands, CRI minimum, wattage. |
| `routes_to` | Select: (none) / Catalog only | For example, "Accessories & parts" goes straight to the filtered catalog. |
| `is_no_preference` | Check | The answer does not filter products ("Not sure", "No preference"). It cannot carry value maps, and Coverage ignores it. |
| `is_active` | Check | |

`ilL-Child-Finder-Condition` (question-level and option-level visibility, replacing `visibleWhen`, `skipWhen` and `hideWhen`)

| Field | Type | Notes |
|---|---|---|
| `applies_to` | Select: Show question when / Skip question when / Hide option when | |
| `option_value` | Data | Required for "Hide option when". |
| `group` | Select: All / Any | How rows with the same `applies_to` and `option_value` combine. |
| `depends_on_question` | Link `ilL-Finder-Question` | Must come earlier in `sequence` (validated, which prevents cycles). |
| `operator` | Select: equals / not equals / in / > / ≥ / < / ≤ / answered / not answered | |
| `value` | Data | Comma-separated for `in`. |

`ilL-Child-Finder-Value-Map` (the Desk-maintained mapping, decision 2; same pattern as `ilL-Child-Driver-Allowed-Option`)

| Field | Type | Notes |
|---|---|---|
| `option_value` | Data | Must equal one of the question's option values (validated). |
| `attribute_doctype` | Select (limited to the facet's allowed DocTypes, §7.1) | |
| `attribute_value` | Dynamic Link → `attribute_doctype` | So staff can only pick real ERP records. |
| `notes` | Data | |

`ilL-Finder-Glossary-Term`: `term_key` (unique), `label`, `tooltip`, `learn_more` (Text Editor), `references` (Small Text).

### 6.2 Validation (controllers)

- Option values must be unique per question. A Family chooser question must have exactly one active instance and the lowest `sequence`.
- Conditions may reference only earlier, active questions. Operators must suit the referenced question's type.
- Value maps: `option_value` must exist on the question, and `attribute_doctype` must be allowed by the facet registry. A facet with a `derive` rule (for example, light type from `LED Package.spectrum_type`) does not need value maps.
- `swatch_color` must match a hex or `linear-gradient(...)` pattern before it is rendered into a style attribute.
- `on_update` and `on_trash` of every finder DocType bump `definition_version` and clear the `ill_product_finder:*` cache keys.

### 6.3 Desk experience

- **Workspace "Product Finder"** with shortcuts: Settings, Questions (list sorted by sequence, showing families, mode, active), Glossary, Coverage report, Verification queue and Sessions report.
- On the question form:
  - **Preview** (shipped in PR 2) renders the question as dealers see it, from the unsaved form.
  - The **Preview matches** button (PR 3, needs the matching engine) opens a dialog. Staff pick answers for this and earlier questions, and see the match, verify and excluded counts per family plus the first 20 products.
  - **Coverage for this question** lists facet values found on products that have no mapping.
- On Settings, the **Open preview** button opens `/portal/product-finder?preview=1`. Staff only. It includes inactive questions, labelled "Draft".

### 6.4 Seeding (patch `patches/seed_product_finder.py`, idempotent)

- Copy seed content into the app package so the patch does not depend on `tools/` at runtime: `illumenate_lighting/illumenate_lighting/product_finder/seed/{questions.json,glossary.json}`.
- Option images are converted to WebP at 400 px and served from `/assets/illumenate_lighting/product_finder/options/*.webp`. Option `image` fields store that URL. Staff can upload a replacement.
- The patch creates the family chooser (§9.1), the family question sets (§9.2) and the glossary terms.
- **Best-effort value maps.** For each option, match its label case-insensitively against the facet's attribute DocType names, labels and codes, with synonyms (Silver ↔ Anodized Silver, Drywall ↔ Plaster-In). Anything unresolved is left empty and appears in the Coverage report.
- It sets `portal_enabled = 0` and `public_enabled = 0`. Staff turn them on after reviewing coverage.

---

## 7. Phase 2 — Matching engine

Package: `illumenate_lighting/illumenate_lighting/portal/product_finder/` with modules `definition.py`, `facets.py`, `facts.py`, `matcher.py`, `prefill.py` and `sessions.py`.

### 7.1 Facet registry (`facets.py`, owned by engineering)

| Facet | Families | Value type | Source | Allowed mapping DocTypes |
|---|---|---|---|---|
| `family` | all | set | `product_type` → family alias | — |
| `application` | all | set | `product_category` (ilL-Webflow-Category) | ilL-Webflow-Category |
| `environment_rating` | Linear, Tape, Neon, Kit | rank | Attribute links "Environment Rating"; template allowed options | ilL-Attribute-Environment Rating |
| `ip_rating` | Tape, Neon, Sheet | rank | Tape/neon allowed options (IP Rating), `ilL-Spec-LED Sheet`. **Linear: unknown → Verify.** | ilL-Attribute-IP Rating |
| `light_type` | Linear, Tape, Neon, Sheet | set | **Derived** from `ilL-Attribute-LED Package.spectrum_type`: Static White → Static white; Tunable White → Tunable white; Dim to Warm → Dim-to-warm; RGB / RGB+W / RGBW / RGB+TW / RGBTW → Full-color | ilL-Attribute-LED Package (override map) |
| `color_mode` | Linear, Tape, Neon | set | LED Package `is_pixel` → "Addressable pixel"; full-color non-pixel → "Analog RGB/RGBW" | ilL-Attribute-LED Package |
| `cct` | Linear, Tape, Neon, Sheet | set of kelvin | Attribute links CCT → `ilL-Attribute-CCT.kelvin` | ilL-Attribute-CCT |
| `cct_range` | Tunable products | min/max kelvin | Min/max kelvin of the CCTs | — |
| `cri_min` | Linear, Tape, Neon, Sheet | number | Attribute links CRI → `ilL-Attribute-CRI.minimum_ra` | ilL-Attribute-CRI |
| `lumens_per_ft` | Linear, Tape, Neon | set of numbers | Output Level → `ilL-Attribute-Output Level.value` (fixture-level for linear) | — |
| `mounting_method` | Linear, Kit | set | Attribute links / kit allowed options | ilL-Attribute-Mounting Method |
| `lens_appearance` | Linear, Kit | set | Attribute links / kit allowed options | ilL-Attribute-Lens Appearance |
| `finish` | Linear, Neon, Kit | set | Template / kit allowed options | ilL-Attribute-Finish |
| `dimming_protocol` | Linear, Tape, Neon, Sheet, Driver (input), Controller (output) | set | Attribute links "Dimming Protocol"; driver input protocols; controller output protocols | ilL-Attribute-Dimming Protocol |
| `output_voltage` | Tape, Driver | set | Attribute links "Output Voltage"; `ilL-Spec-Driver.voltage_output` | ilL-Attribute-Output Voltage |
| `driver_wattage` | Driver | number (max over variants) | `ilL-Spec-Driver.max_wattage × usable_load_factor` | — |
| `controller_type` | Controller | set | `ilL-Spec-Controller.controller_type` | — (Select values) |
| `channels`, `zones` | Controller | number | Controller spec | — |
| `wireless_protocol` | Controller | set | Controller spec wireless protocols | (that protocol DocType) |
| `controller_mounting` | Controller | set | `mounting_type` | — |

Adding a facet is a code change and a PR. Mapping values onto it is Desk work.

### 7.2 Product facts (`facts.py`)

- `build_facts()` reads all active `ilL-Webflow-Product` records with `capability in (configure, quantity)`, in batched queries (no per-product `get_doc` in a loop). It joins attribute links, templates and their allowed options, specs and the attribute masters.
- Each product gets a dict: `{name, slug, family, image, title, short_description, facets: {facet: value | None}, sources: {facet: "attribute_link" | "template" | "derived"}}`. `None` means **unknown**.
- Cache key: `ill_product_finder:facts:<definition_version>:<catalog_stamp>`. `catalog_stamp` is the max `modified` across Webflow products, templates and specs, computed cheaply. TTL is 1 hour.
- `doc_events` on those DocTypes clear the key. Reuse the existing `webflow_sync_events.on_attribute_update` hook entries and add Webflow product and template hooks.
- The rollout gate is applied per request, so the shared cache never leaks capability across users.

### 7.3 Matching (`matcher.py`)

`match(definition, answers, *, user_scope) -> Result`

1. `answers = prune(definition, answers)`. Use the same visibility semantics as `engine.js`, against the Desk conditions.
2. Restrict to the families chosen in the family question. "Not sure" counts as Linear Fixture.
3. For each product and each answered question with a facet:
   - **Hard:** comparison passes → keep. Fails → exclude, and record `{question, answer, reason}` for "why excluded". **Facet unknown** → apply `unknown_policy` (default **Verify**): keep the product and append a verification reason, rendered from `verification_reason_template`, for example "IP67 rating".
   - **Soft:** pass or fail is recorded for scoring. Unknown counts as a neutral pass plus a verification reason, if the policy is Verify.
4. Scoring is ported from `recommend.js`:
   - Base 50.
   - Lumens band within → +20, otherwise a closeness score.
   - CCT pass +12 / fail −6.
   - CRI pass +10 / fail −8.
   - Finish/lens pass +4 each.
   - **Verification needed −5**, so verified matches rank first when scores are otherwise equal.
   - Clamp to 0–100.
5. **Relaxation:** if no product passes every soft check, drop soft questions in `relax_priority` order until some survive, and report the relaxed labels.
6. **Companions:** compatible drivers (dimming protocol plus output voltage), controllers for the chosen protocol, and `compatible_products` rows of the top 10 matches, de-duplicated. Each companion carries a reason ("Powers 24 V tape with 0-10V dimming").
7. Return:

```python
{
  "matches": [{"name", "score", "reasons": [...], "tradeoffs": [...], "verify": [...], "best": bool}],
  "companions": [{"name", "relation"}],
  "relaxed": ["CRI requirement"],
  "counts": {"match": 7, "verify": 3, "excluded": 41, "by_family": {...}},
  "no_hard_match": False,
  "eliminated_by": None,
}
```

`evaluate(definition, answers, question_key)` returns `{match_count, verify_count, option_counts: {value: {match, verify}}, disabled: [{value, reason}]}` for the question being answered. It caches per `(definition_version, catalog_stamp, normalized answers)` for 10 minutes.

### 7.4 Pre-fill (`prefill.py`)

`prefill_for_template(family, template, answers) -> {selections, unmatched: [...]}` maps answers to **codes the template allows** for each family:

| Family | Selections it can fill |
|---|---|
| Linear | `environment_rating_code`, `cct_code`, `lens_appearance_code`, `finish_code`, `mounting_method_code`, `led_package_code`; `delivered_output_value` from the lumen band |
| Tape / Neon | `environment_rating`, `cct`, `output_level`, `finish` |
| Sheet | CCT and IP |
| Kit | finish, lens, mounting |
| Driver | `voltage_output`, `input_protocol`, smallest `wattage` ≥ requirement |
| Controller | `controller_type`, `output_protocol`, `wireless_protocol`, `mounting_type` |

It never invents a value that is not in the template's allowed options.

---

## 8. Phase 3 — Sessions, APIs and security

### 8.1 Extend `ilL-Configurator-Session`

| Field | Change |
|---|---|
| `user` | Becomes optional (empty for unclaimed guest sessions). |
| `product_type` | Becomes optional; adds Extrusion Kit, Driver, Controller and Mixed. |
| `source` | New. Select: Portal / Webflow. |
| `brand` | New. Link ilL-Webflow-Brand (public only). |
| `definition_version` | New. Int. |
| `quiz_answers` | Changes from Long Text to **JSON**. Validated and capped at 16 KB. |
| `result_json` | New. JSON (matches, companions, relaxed, counts). |
| `result_computed_at`, `completed_on`, `claimed_on` | New. Datetime. |
| `status` | Becomes `Active` → `Completed` → `Used` / `Expired`. |

- **Permissions:** add `has_permission` and `permission_query_conditions` hooks. Users see only their own sessions. ilL Product Finder Manager, System Manager and sales staff see all.
- The portal API always resolves a session by `session_token` **and** `user == session.user`. Guest access works only through the public API with a guest token, and only while `user` is empty.
- **Scheduler (daily):** mark user sessions untouched for `session_expiry_days` and unclaimed guest sessions older than 7 days as `Expired`. Delete expired guest sessions after 30 more days.
- `api/configurator_session.save_session` and `get_latest_session` become thin wrappers over the new service. They reject Guest and drop the explicit `frappe.db.commit()`.

### 8.2 Portal API (`api/product_finder.py`)

Every endpoint requires login, `require_catalog_access()` and `portal_enabled`.

| Endpoint | Verb | Purpose |
|---|---|---|
| `get_definition(preview=0)` | GET | Active questions in sequence, options, conditions, glossary, version and Settings copy (banner, verification text). `preview=1` is staff only and includes drafts. |
| `start(import_answers=None)` | POST | New session → `{token}`. |
| `get_session(token)` | GET | Answers, status, stale flag. |
| `save_answers(token, answers)` | POST | Autosave, validated against the definition. Rate limit 60/min/user. |
| `evaluate(answers, question_key)` | POST | Live counts. Rate limit 120/min/user. |
| `complete(token)` | POST | Runs `match`, stores the result, returns `{catalog_url, top: [...], counts}`. |
| `claim(token)` | POST | Attaches an unclaimed guest session to the current user (decision 6). |
| `dismiss_banner()` | POST | Sets user default `ill_finder_banner_dismissed = <definition_version>`. A new campaign version shows the banner again. |
| `request_verification(token, product_slug, schedule=None, line_key=None, message=None)` | POST | Creates or reuses an `ilL-Product-Verification-Request` (§14.3). |

**Answer validation:** keys must be known active question keys; values must be among the visible options; numbers within min/max; range low ≤ high; at most 40 keys and 16 KB. Invalid input → `frappe.ValidationError` with a field-level message.

### 8.3 Public API (`api/product_finder_public.py`, decision 6)

Every endpoint is `allow_guest=True`, requires `public_enabled`, and requires a brand from `public_brands`. CORS uses the existing `utils.after_request` and `ALLOWED_ORIGINS`.

| Endpoint | Verb | Limit | Purpose |
|---|---|---|---|
| `get_definition(brand)` | GET | 60/min/IP | Same shape as the portal, with no staff fields. |
| `evaluate(brand, answers, question_key)` | **GET** (answers JSON in the query, ≤ 4 KB) | 120/min/IP | Counts against **published** products only. |
| `complete(brand, answers)` | POST | 10/min/IP | Creates a guest session (`source=Webflow`, `user` empty). Returns results with **no prices**: title, image, Webflow product URL (`webflow_brand.get_base_url(brand)` + collection slug + product slug), reasons and verification chips. Also returns `claim_url = <portal>/portal/product-finder?claim=<token>`. |

- **Published** means: active, configurable or quantity capability, `target_brands` has the brand enabled, and that brand's `sync_targets` row is `Synced`.
- The React app calls these with `credentials: 'omit'`. They therefore always run as Guest, which avoids Frappe's CSRF check for logged-in cookies on cross-origin POSTs.

---

## 9. Phase 4 — Product-type routing with Linear Fixture emphasis (decision 5)

### 9.1 Question 1: "What are you looking for?" (Family chooser)

| Option | Card | Subtitle | Behavior |
|---|---|---|---|
| **Linear Fixture** | **Large featured card** with a hero image and the badge "Most popular — not sure? Start here" | "A complete light: channel, lens and LED built to your length." | Linear question set |
| LED Tape | Standard card | "Flexible LED strip for coves, shelves and under-cabinet." | Tape set |
| LED Neon | Standard card | "Smooth, dot-free neon-style lines for signs and accents." | Neon set |
| LED Sheet | Standard card | "Even backlighting panels for signs and countertops." | Sheet set |
| Extrusion Kit | Standard card | "Channel, lens and end caps to pair with your own tape." | Kit set |
| Power Supply (Driver) | Standard card | "Powers and dims your LED products." | Driver set |
| Controller | Standard card | "Wall controls, wireless and DMX control." | Controller set |
| Accessories & parts | Compact link | "Connectors, clips, end caps and more." | `routes_to = Catalog only`: goes straight to `/portal/products?type=Accessory,Component` |
| "I'm not sure" | Text link under the Linear card | — | Selects Linear Fixture |

Layout: on desktop the featured card spans two columns at the top, with a 3-column grid below. On mobile the featured card comes first at full width. Keyboard and screen-reader order matches the visual order.

### 9.2 Seeded question sets per family (staff can edit all of them)

| Family | Questions, in order (★ = new, ⚑ = unknown data falls back to Verify) |
|---|---|
| Linear Fixture | ★Where is it going (application) → indoor/outdoor → moisture → IP rating ⚑ (damp/wet) → light type → color mode (full color) → purpose (lumen band) → installation method → CCT range (tunable) → CRI → dimming protocol → diffuser → finish |
| LED Tape | application → indoor/outdoor → moisture → IP rating → light type → color mode → purpose → CCT range → CRI → dimming protocol |
| LED Neon | application → indoor/outdoor → moisture → IP rating → light type → color mode → purpose → dimming protocol → finish |
| LED Sheet | ★What will it backlight (signage, countertop, ceiling/wall) → indoor/outdoor → IP rating → light type → CCT range → dimming protocol |
| Extrusion Kit | installation method → moisture ⚑ → diffuser → finish |
| Driver | ★What will it power (tape/neon/fixtures, informational) → dimming protocol (input) → ★output voltage (24 V default, "Not sure → 24 V") → ★load: a Number in watts **or** the helper "run length (ft) × W/ft", which computes watts and adds 20% headroom → ★location (dry/damp/wet) ⚑ |
| Controller | ★How do you want to control it (wall keypad, phone/app wireless, DMX console, existing 0-10V dimmer) → light type (sets the channel requirement: 1 / 2 / 3–4 / pixel) → ★number of zones → wireless protocol (when wireless) → mounting type |

Rules carried over from the prototype: Outdoor hides Dry; picking addressable pixel hides 0-10V, TRIAC, ELV and DALI; "Not sure" options exist on technical questions and map to "no constraint".

### 9.3 After the quiz → the right configurator

- The results CTA **See matching products** opens the catalog filtered to the chosen family plus a companions tab.
- The results CTA **Configure the top match now** opens the top match's family configurator with pre-fill (§12.3).
- From any product page, the action panel always opens **that product's family configurator** (§13).

### 9.4 `/portal/configure` with no category shows the same chooser

- In `configure.py`, when there is no `category`, no `template` and no `initial_request` (a reopened line), render a new chooser partial, `templates/includes/product_type_chooser.html`, instead of defaulting silently to Linear Fixture.
  - It shows the same cards and emphasis as §9.1, from the Desk family question options, so the images and copy match.
  - Card links keep `schedule`, `line_key`, `line_idx` and `draft`.
  - It adds a link: "Not sure what you need? Take the Product Finder".
- Pending schedule lines that link to `/portal/configure?schedule=…&line_key=…` without a category (`schedule.html:1250`) now reach the chooser.
- Existing links with a category behave as before.
- The LED Sheet category pills in `configure.html:36-43` are replaced by the chooser's compact variant ("Change product type") for every family.

---

## 10. Phase 5 — Finder UI (React)

### 10.1 Modes and configuration

`window.IllConfigurator.mount(el, config)`:

```js
{
  mode: 'portal' | 'public',
  apiBase: '' /* portal */ | 'https://<erp>' /* public */,
  brand: 'illumenate',      // public only
  csrfToken,                // portal only
  sessionToken,             // portal resume
  claimToken,               // portal claim
  preview: false,           // staff preview
  catalogUrl: '/portal/products'
}
```

### 10.2 Code changes in `tools/configurator_ui`

1. `src/lib/api.js`: a client for both modes. Portal mode uses same-origin requests with `X-Frappe-CSRF-Token`. Public mode uses `credentials: 'omit'`.
2. `src/lib/definition.js`: fetch the Desk definition and adapt it to the shape `engine.js` expects (conditions → `visibleWhen`/`skipWhen`/`hideWhen`). `engine.js` stays pure and is unit-tested against the same fixtures as the Python `prune()`.
3. Remove `src/data/*.seed.json`, `competitors.sample.json`, `recommend.js`, `resultObject.js` and `CompareTable.jsx` (decisions 3 and 6). Remove `configureHandoff.js`; the portal flow replaces it.
4. `src/content/*.json` move to `seed/` and are no longer imported at runtime.
5. `QuestionStep.jsx`:
   - Images come from `option.image` URLs, so the static import map goes away.
   - Add a `FamilyChooser` variant with a featured card.
   - Option cards show `match` / `verify` counts from `evaluate()` ("12 products · 3 need a check").
   - Disabled options explain why ("No products for Wet + Recessed").
6. `Wizard.jsx`:
   - Debounced autosave (500 ms).
   - Resume from `sessionToken`.
   - `preview` shows "Draft" badges.
   - Focus moves to each newly revealed question heading.
   - Respect `prefers-reduced-motion`.
   - Sticky offset below the portal navbar.
7. `Results.jsx`, rewritten:
   - A heading with counts by family, the relaxation notice, the top three cards, and amber verification chips with the Settings copy.
   - **Portal:** "See matching products" and "Configure the top match now", plus "Edit answers" and "Start over".
   - **Public:** product cards linking to Webflow pages and "Configure & add to a project (dealers)" → `claim_url` via login.
   - No JSON export, competitor table or "prototype" footer.
8. Accessibility: option cards are `button`s with `aria-pressed`; groups get `role=radiogroup` or `group`; tooltips are keyboard reachable (already in place); text contrast ≥ 4.5:1 on swatches (dark text on light swatches, light text on dark).
9. Style isolation: keep `important: '#ill-configurator-root'` and preflight disabled. Add scoped resets wherever Bootstrap's `.btn`, `label` or `input` styles leak in. Verify on the portal page.

### 10.3 Builds and shipping

| Script | Config | Output | Used by |
|---|---|---|---|
| `build:portal` | `vite.portal.config.js` (IIFE, `base: /assets/illumenate_lighting/product_finder/`) | `illumenate_lighting/public/product_finder/portal/` | `/portal/product-finder` |
| `build:public` | `vite.config.js` (IIFE) | `illumenate_lighting/public/product_finder/public/` | The Webflow `<script>` tag points to `https://<erp>/assets/illumenate_lighting/product_finder/public/ill-configurator.js`, so one source is hosted by the ERP. |
| `build:preview` | unchanged | `dist-preview/` | Vercel preview (optional) |

- Built output is **committed**, because Frappe Cloud's `bench build` does not run Vite or Tailwind.
- CI job `product-finder-bundle`: `npm ci && npm run build:portal && npm run build:public && git diff --exit-code illumenate_lighting/public/product_finder`.
- `tools/check_portal_templates.py` adds the new templates.

---

## 11. Phase 6 — Dashboard banner and entry points

- `portal.py` adds to the context:
  - `finder_enabled` = Settings `portal_enabled` and `can_view_catalog`.
  - `finder_banner` = Settings copy and image, shown when `banner_enabled` and the user's dismissed version is not the current version.
  - `finder_resume` = the latest `Active` session, with its progress percentage.
- `portal.html`, between the hero and the cards:

```
┌────────────────────────────────────────────────────────────────────────────┐
│ [img]  Not sure which fixture fits your project?                      [×] │
│        Answer a few picture-guided questions and we'll show you the       │
│        products that fit.        [Start the Product Finder]  Browse catalog│
└────────────────────────────────────────────────────────────────────────────┘
```

  - About 96 px tall on desktop, stacked on mobile.
  - With `finder_resume`, the CTA reads "Resume (60% done)".
  - × calls `dismiss_banner()` and fades the banner out.
- Other entry points:
  - Nav link **Product Finder** (C10).
  - **Help me choose** in the catalog header.
  - The chooser's "Take the Product Finder" link (§9.4).
  - A small Product Finder card on the dashboard when the banner is dismissed.
- Page: `templates/pages/product_finder.{py,html}` with route `/portal/product-finder`.
  - Guest → login redirect (keeps `claim`).
  - No catalog access → `/portal/request-dealer-access`.
  - Disabled → `/portal/products`.
  - Mounts the portal bundle with `sessionToken` (from `?session=`, owned by the user), `claimToken` (from `?claim=`) and `preview` (staff only).

---

## 12. Phase 7 — Catalog and product page with finder context

### 12.1 Catalog API

`get_catalog_products(..., finder=None, sort=...)`:

- Resolve the owned session. If `result_json` is missing or stale (definition version or catalog stamp changed), recompute it.
- Restrict with `` `tabilL-Webflow-Product`.name IN %(finder_names)s ``. Add `sort="relevance"`, ordering by score with a parameterized `CASE`; it is the default with a finder.
- Add `match: {score, reasons, tradeoffs, verify, best}` to each product. Return a `finder` block: `{token, answer_chips: [{question, label}], relaxed, counts, companions_count, family}`.
- `view="companions"` returns the companion products with their `relation`.
- Normal search and attribute filters still narrow the finder set. Facets (C7) are scoped to it.

### 12.2 Catalog UI

- A **finder banner**:
  - "Showing **7** products that fit your answers · 3 need a quick check with our team".
  - Answer chips (Outdoor · Wet · IP67 · Static white · Surface · 0-10V).
  - **Edit answers** (`/portal/product-finder?session=<token>`), **Show all products** and **Start over**.
  - The relaxation notice, when criteria were relaxed.
- Tabs: **Recommended (7)** | **Drivers, controllers & accessories (5)** | **All products**.
- Cards:
  - A "Best match" badge on the top card.
  - Up to two green "Why it fits" chips.
  - An **amber "Verify with our team"** chip with a tooltip listing the reasons.
  - Every link carries `?finder=<token>`.
- Empty result: "No products match **Wet + Recessed + DMX**." Offer **Edit answers**, which jumps to the eliminating question, and **Ask our team**, which calls `request_verification` with no product to create a general request.

### 12.3 Product page

- With `?finder`:
  - A **"Why this product fits"** box.
  - The **verification callout** (§14.2) when it applies, with **Ask our team to verify now**.
  - The breadcrumb gets "← Your matches".
- **Configure:** the URL gets `finder=<token>`. `configure.py` loads the owned session, calls `prefill_for_template(family, template, answers)` and sets `initial_request = {template, selections}`.
  - The "pre-filled" banner lists what was pre-filled and anything that could not be applied ("Finish *White* is not offered on this product").
  - Legacy `quiz_handoff` parameters are converted with the same function.
- **Add to schedule** (quantity products): unchanged flow, plus inline project/schedule creation (C11). Driver and controller products now use their configurator first (§13).
- **Pairs well with:** companion cards, each with quick **Add to schedule**.

---

## 13. Phase 8 — Configurators for every family (decision 5)

### 13.1 Projection and catalog capability

- In `product_projection.py`, extend `TEMPLATE_FIELDS` with `"Extrusion Kit": "kit_template"`, `"Driver": "driver_template"` and `"Controller": "controller_template"`.
- `configure_url = /portal/configure?category=<family>&template=<code>&product_slug=<slug>`.
- Add a `kit_template` Link field to `ilL-Webflow-Product` (`depends_on: product_type == 'Extrusion Kit'`), with a back-link sync in `_update_template_backlink`.
  - Patch `backfill_kit_template_links.py` fills it from `ilL-Extrusion-Kit-Template.webflow_product`.
- Add Extrusion Kit, Driver and Controller to `configure._normalize_product_category`, `FAMILY_ALIASES` and the rollout family list.

### 13.2 Driver and Controller configurator (portal)

- Partial `templates/includes/configurator_driver_controller_form.html`.
- JS class `IllConfigurator.DriverController` in `public/js/configurator/driver_controller_steps.js`, extending the shared Base and added to `illumenate_web.bundle.js`.
- Steps come from `get_driver_configurator_init` / `get_controller_configurator_init`, with cascading through `get_*_cascading_options`. Each step is a picture/pill selector with the glossary help used by the finder.
- **Validate** calls `validate_*_configuration`, which gives the variant, the spec, an **orderable Item** and MSRP pricing for dealers.
- **Save** goes through a new `portal/standard_products.add_configured(product_slug, selections, schedule_name, quantity, line_id, location, notes, expected_modified, idempotency_key, finder=None)`:
  - Re-validates on the server and resolves the variant's Item.
  - Asserts the Item is in `choices(product)`.
  - Writes an ACCESSORY line with `variant_selections = {product_slug, template, selections, variant_code, item_code}`.
  - Uses the same receipts and idempotency as `add`.
- Pre-fill comes from §7.4. Schedule context and line metadata come from the draft pattern the other configurators already use.

### 13.3 Extrusion Kit configurator (portal)

- Partial `templates/includes/configurator_kit_form.html`.
- JS class `IllConfigurator.Kit` in `public/js/configurator/kit_steps.js`, ported from the Desk dialog in `ill_project_fixture_schedule.js:234-560`:
  - Steps: Finish → Lens → Mounting → Endcap style and color.
  - A live preview of the kit composition, MSRP and stock (`get_kit_component_stock`).
- **Save** goes through `portal/kit_configuration.save` (C15). It re-validates on the server, prices on the server, and is idempotent. The Desk dialog moves to the same service.

### 13.4 Configure page wiring

- `configure.py` branches on the three new categories and renders their partials inside the existing schedule target card and draft handling.
- `title_map` gets "Configure Power Supply", "Configure Controller" and "Configure Extrusion Kit".

---

## 14. Phase 9 — "Needs verification" workflow (decision 1)

### 14.1 When a product needs verification

- The product passed every hard rule it has data for, **and** at least one answered question's facet is **unknown** for that product, **and** the question's `unknown_policy` resolves to **Verify** (the default).
- Example: a Linear Fixture for "Outdoor · Wet · IP67". Linear products have no IP data, so the reason is "IP67 rating".
- It is computed **only on the server**, from the session's answers and the product's facts, at match time and again at save time.

### 14.2 Warning copy and placement

The default text is set in Desk Settings and can be edited there.

> **Most likely a fit — our team will confirm.**
> Based on your answers, we can most likely build this for your project, but our team needs to verify the **{reasons}** before you continue to quoting and ordering. You can keep configuring and adding it to your schedule now. We'll confirm before your quote is issued.

Where it appears:

| Place | Treatment |
|---|---|
| Quiz results card | Amber chip: "Needs a quick check" |
| Catalog card | Amber chip: "Verify with our team" (tooltip: reasons) |
| Product page | Callout as above, with **Ask our team to verify now** (optional message) |
| Configurator | Slim amber notice above the save button |
| Schedule line | Badge: "Verification pending" (amber), "Verified by ilLumenate" (green), "Not feasible — see message" (red) |

### 14.3 Data model

New DocType **`ilL-Product-Verification-Request`**, named `PVR-.YYYY.-.#####`:

| Field | Type |
|---|---|
| `state` | Select: REQUESTED / UNDER_REVIEW / INFORMATION_NEEDED / VERIFIED / NOT_FEASIBLE / CANCELLED |
| `product` | Link ilL-Webflow-Product |
| `family` | Data |
| `finder_session` | Link ilL-Configurator-Session |
| `reasons` | JSON (`[{question_key, question_label, answer, reason}]`) |
| `answers_snapshot` | JSON |
| `schedule` | Link ilL-Project-Fixture-Schedule (optional) |
| `line_key` | Data (optional) |
| `project` | Link ilL-Project |
| `customer` | Link Customer |
| `requested_by` | Link User |
| `message` | Small Text |
| `assigned_to` | Link User |
| `due_date` | Date (default: +2 business days) |
| `resolution` | Small Text |
| `resolved_by` | Link User |
| `resolved_on` | Datetime |

- Permissions: the requester and same-company dealers can read; staff with the sales or engineering capability can write. Implement it like `portal/quotes.has_permission`.
- Add it to `conversations.PARENTS` so dealers and staff can message each other on it. Staff are the sales or engineering capability.
- Add it to `queues.QUEUES` as `"verification"` (capability `sales`, open states REQUESTED, UNDER_REVIEW and INFORMATION_NEEDED, owner `assigned_to`, due `due_date`).

New fields on **`ilL-Child-Fixture-Schedule-Line`**:

| Field | Type |
|---|---|
| `verification_status` | Select: (blank) / Pending / Verified / Not Feasible |
| `verification_reasons` | Small Text (JSON) |
| `verification_request` | Link ilL-Product-Verification-Request |
| `finder_session` | Link ilL-Configurator-Session |

### 14.4 Writing the flags

- `portal/configuration.save`, `standard_products.add`, `standard_products.add_configured` and `kit_configuration.save` accept an optional `finder` token.
- With it, the server loads the owned session, recomputes the verification reasons for **this** product, and then:
  - **No reasons:** clear the fields.
  - **Reasons, and a VERIFIED request already exists** for the same product, session and reasons: set `verification_status = Verified` and link the request.
  - **Otherwise:** set `Pending`, create or reuse a request with `schedule` and `line_key`, and link it.
- Reconfiguring a line with a different product or answers recomputes the flags. A Pending request with no lines left is set to CANCELLED.
- Staff resolving a request (VERIFIED or NOT_FEASIBLE) update every linked line, notify the requester through `portal/notifications.py`, and post a conversation message.

### 14.5 Gates (`verification_gate` setting; default "Before quote is issued and order is placed")

| Action | Behavior with Pending or Not Feasible lines |
|---|---|
| Dealer adds or edits lines | Allowed |
| Dealer **Request Quote** (`portal/quotes.request_quote`) | Allowed. The snapshot includes `verification_status` and `verification_reasons` (add them to `LINE_FIELDS`). The quote request page shows "3 lines awaiting verification". |
| Staff **prepare quotation** (`offers.prepare_quotation`) | Allowed, with a banner listing the pending lines and links to the requests |
| Staff **submit quotation** (`offers.before_submit`) | **Blocked**: "Verify or remove the lines that need verification before issuing this quote" |
| Dealer **accept offer** (`offers.respond` ACCEPT) and **order intake** (`order_intake.submit`) | **Blocked** with the same message (defense in depth) |
| Desk `quote_from_schedule.add_schedule_to_quotation` | Warns with a msgprint listing the lines; it does not block. Staff are doing the review. |

"Before order only" moves the quotation block to a warning. "Warning only" shows warnings everywhere and blocks nothing.

---

## 15. Phase 10 — Public Webflow quiz on live data (decision 6)

1. Ship `build:public` and the endpoints in §8.3. The staging Webflow site (`illumenate-staging.webflow.io`, already in `ALLOWED_ORIGINS`) points its script tag at the staging ERP asset URL.
2. The public results show published products only, with no prices, linking to Webflow product pages.
3. The **dealer path**: "Configure & add to a project" goes to `<erp>/login?redirect-to=/portal/product-finder?claim=<token>`. After login, `claim()` attaches the session and redirects to `/portal/products?finder=<token>`. Non-dealers land on `/portal/request-dealer-access`, with the claim kept for after approval.
4. Retire the Vercel-hosted seed build: delete the seed data and update `README.md` and `docs/WEBFLOW_INTEGRATION_GUIDE.md`.
5. Abuse controls:
   - Rate limits and the 4 KB GET cap.
   - Guest sessions are created only by `complete`.
   - Guest results never include stock, pricing or unpublished products.

---

## 16. Staging deployment and rollout (decision 4)

1. Merge each PR to `staging` and deploy it to the staging site. Run `bench migrate`, which installs the DocTypes and seed patch, and `bench build`.
2. Run the C4 dry run, then the repair. Confirm the **Catalog Configurability** report shows linear, tape, neon, sheet and (after §13) kit, driver and controller products as `ok`.
3. Staff complete the value maps until the **Product Finder Coverage** report has no unmapped values on active products.
4. Staff turn on `portal_enabled`, then `banner_enabled`. Internal users run through the acceptance script in §18.
5. Turn on `public_enabled` for the staging Webflow brand and test the claim path.
6. When staging is signed off, repeat steps 1–5 on production. No production-only code paths.

---

## 17. Test plan

| Layer | Location | Cases |
|---|---|---|
| Python unit | `tests/portal_unit/test_contracts.py` | C1 option shapes; C2 reasons; the new families' configure URLs. |
| Python unit | **new** `tests/portal_unit/test_product_finder.py` | Definition loading and condition evaluation, matching `engine.js` on shared fixtures; answer validation (unknown keys, hidden-option values, ranges, size); hard rank comparisons; **unknown → Verify / Exclude / Include**; scoring order (verify −5); relaxation order; companions; `evaluate` counts and disabled reasons; pre-fill only uses template-allowed codes; session ownership, claim and expiry. |
| Python unit | **new** `test_product_verification.py` | Flags computed at save; reuse of a VERIFIED request; recompute on reconfigure; resolution propagates to lines; each gate (quote submit, offer accept, order intake) under each `verification_gate` value. |
| Python unit | **new** `test_kit_and_driver_saves.py` | C15: a forged `configuration_result` is rejected or re-derived; the driver/controller variant Item must be in `choices`; idempotent retries. |
| DOM (node:test + jsdom) | `tests/portal_ui/catalog.test.cjs`, `standard_products.test.cjs`, **new** `product_finder.test.cjs` | C5, C6; finder banner chips, tabs and links carry `finder`; verification chips; product page callout and "Ask our team"; configure URL carries `finder`; banner dismiss; chooser on `/portal/configure` keeps schedule and draft parameters. |
| React (add `vitest`) | `tools/configurator_ui` | `engine.js` against the shared fixtures; `FamilyChooser` featured layout and keyboard order; evaluate debounce; portal and public results CTAs; no competitor table in either build. |
| Installed site | existing installed-site suite | A real generated linear product is configurable; a finder-restricted catalog query; session and verification permission hooks; public endpoints return only published products, no prices, and work with CORS. |
| E2E (Playwright) | `tests/portal_e2e/portal.spec.cjs` | (a) Dealer: banner → Linear → Outdoor/Wet/IP67/Static/Surface/0-10V → catalog shows a verification chip → product → configure pre-filled → save → schedule line "Verification pending" → request quote → staff verify → line "Verified". (b) Driver path: chooser → driver questions → product → driver configurator → add to schedule. (c) Kit path. (d) Accessories card → catalog. (e) `/portal/configure` with no category shows the chooser with Linear featured. |
| Lint and checks | `ruff check .`, `ruff format .`, `tools/check_portal_templates.py`, CI bundle freshness | |

---

## 18. Work breakdown: PR sequence and acceptance criteria

| PR | Contents | Acceptance criteria |
|---|---|---|
| **1. Catalog fixes** | §5 C1–C14 (C12 redirect lands with PR 6) | A seeded linear product shows the configurator on its product page; staff see the reason for any inquiry product; numeric filters work; unknown query parameters are ignored; guests are redirected; nav has Products; a dealer can create a schedule from the product page. |
| **2. Finder content in Desk** | §6 DocTypes, validation, workspace, preview dialog, seed patch, Coverage report | `bench migrate` creates all records from the seed; staff can edit an option image and see it in the preview; invalid conditions or mappings are rejected; the Coverage report lists unmapped values. |
| **3. Engine, sessions, APIs, verification model** | §7, §8.1–8.2, §14.3 DocType and line fields, queue and conversations registration | Python unit suite green; `evaluate` returns correct counts for the seeded fixtures; sessions are owner-only. |
| **4. Finder UI and entry points** | §9.1–9.2, §10, §11, §9.4 chooser on `/portal/configure` | A dealer completes the Linear path and reaches the filtered catalog; the banner shows, dismisses and resumes; the chooser features Linear; no competitor table; the CI bundle check passes. |
| **5. Catalog and product page integration with the verification UI and gates** | §12, §14.2, §14.4, §14.5 | E2E (a) passes; gates block per setting; staff resolve from the queue and the dealer is notified. |
| **6. Kit, driver and controller configurators** | §13, C12, C15 | E2E (b) and (c) pass; forged kit payloads are rejected; the Desk kit dialog still works through the new service. |
| **7. Public quiz on live data** | §8.3, §15 | The staging Webflow page runs the live quiz; the claim path lands a dealer on the filtered catalog; the seed files are deleted. |

PRs 1 and 2 can be developed in parallel. PR 3 depends on PR 2. PRs 4 and 6 depend on PR 3 and can run in parallel. PR 5 depends on PRs 3 and 4. PR 7 depends on PRs 3 and 4.

---

## 19. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Missing or inconsistent product data makes results look wrong | The Coverage report is a go-live gate; unknown data defaults to Verify, so nothing is hidden for lack of data; staff preview before enabling. |
| Desk edits break the quiz (for example, a condition pointing at a removed option) | Controller validation; `definition_version` bump plus stale-session detection; the UI falls back to "This question changed — please re-answer". |
| Performance of facts and evaluate on every click | Batched facts build, cached per version and stamp; evaluate result cache; 150 ms client debounce; rate limits. |
| The committed bundle drifts from source | CI freshness job. |
| Bootstrap and Tailwind style clashes in the portal | Scoped Tailwind, scoped resets, and E2E screenshot checks on the finder page. |
| Public endpoint abuse | GET size caps, per-IP rate limits, brand allow-list, published products only, no prices or stock. |
| Kit save tampering (existing issue) | C15 server-side re-validation before any dealer access. |
| Verification gates frustrate dealers | Positive copy, Verify reuse across lines, a 2-business-day due date in the staff queue, and a configurable gate. |

---

## 20. Small decisions taken by default (change in Desk Settings if needed)

- Verification blocks **issuing the quote and placing the order**, not building the schedule or requesting a quote.
- Products needing verification rank just below fully verified matches with the same fit (−5 score).
- The "Not sure" options on technical questions mean "no constraint". "I'm not sure" on question 1 means Linear Fixture.
- A dismissed banner stays hidden until staff change the banner campaign, which bumps `definition_version`.
- Guest sessions expire after 7 days if unclaimed. Portal sessions expire after 30 days of inactivity.
