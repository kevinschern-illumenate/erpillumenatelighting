# Catalog Builder in ERPNext — implementation plan

Status: proposed (2026-10-05). Hand-off document for an engineer or coding agent
with **no prior context**. Each session below stands alone: it lists what to read,
what to build, how to verify it, and what not to touch. Do the sessions in order;
each one ends with a mergeable pull request.

## 0. Goal and background

### What exists today

The **YAML Builder** (`tools/yaml_builder_ui`, React 18 + Vite 6 + Tailwind 3) is a
static web app, currently hosted on Vercel, where staff author product catalogs for
seven families: linear fixtures, LED tape, LED neon, LED sheets, extrusion kits,
drivers and controllers. A catalog is a "version 2" YAML file:

```yaml
schema_version: 2
product_type: extrusion-kit        # fixture | tape | neon | led-sheet | extrusion-kit | driver | controller
series_name: Castle
records:                           # {DocType: [record, ...]}; keys are DocType fieldnames
  ilL-Extrusion-Kit-Template:
    - template_code: KIT-CA01
      allowed_options: [ {option_type: Finish, finish: White, is_active: 1} ]   # child tables are lists
external_links:                    # records that already exist in ERPNext
  ilL-Attribute-Finish: [White]
add_to_reference: true             # optional
```

A Python CLI then validates the YAML and writes numbered ERPNext Data Import CSVs:

```
python -m tools.fixture_builder --config my.yaml --output ./output/my/
```

Staff import each CSV by hand through ERPNext **Data Import** ("Insert New
Records"), in manifest order. Links to pre-existing ERPNext records are resolved
against a **committed snapshot** of the site, `tools/yaml_builder_ui/src/erp-reference.json`
(~4.3 MB), rebuilt from manual DocType exports with
`python -m tools.fixture_builder.erp_reference <exports.zip>`.

Read `tools/yaml_builder_ui/README.md`, `tools/fixture_builder/README.md` and
`tools/fixture_builder/CATALOG.md` first; they are short and current.

### Target workflow

1. Staff open `https://<erp-site>/catalog-builder`, logged in with their normal ERPNext account.
2. Link fields suggest **live** ERPNext records (no snapshot, no exports).
3. **Check** runs a full server-side dry run (every record inserted, then rolled back)
   and lists errors and warnings per record.
4. **Import** inserts every record in dependency order in one transaction and shows
   a results table linking each created record. Any failure rolls back everything.
5. Every Check/Import is logged for audit.

Publishing to Webflow stays a separate, deliberate step (existing
**Readiness and Publication** flow, `docs/B2B_PUBLICATION_RUNBOOK.md`).

### Session map

| # | Session | Delivers | Depends on |
|---|---|---|---|
| 1 | Host the builder inside ERPNext | `/catalog-builder` page, login + role gate, snapshot served by an authenticated endpoint | — |
| 2 | Live ERPNext data | Reference built live from the site; refresh; copy-from-existing fetches full records | 1 |
| 3 | Server import engine | Shared catalog code inside the app, `check`/`import` endpoints, `ilL-Catalog-Import` log DocType | 1 (2 optional) |
| 4 | Import UI | Check / Import buttons, results table, history | 2, 3 |
| 5 | Staging rehearsal and hardening | Real imports of every product family on staging, fixes, docs, Vercel decision | 1–4 |

## 1. Facts about this repository (verified 2026-10-05)

### Stack and layout

- Frappe app `illumenate_lighting` for **Frappe/ERPNext v16** (CI: Python 3.14,
  `FRAPPE_BRANCH: version-16`; `pyproject.toml` requires `frappe >=16.0.0-dev,<17`).
  Hosted on **Frappe Cloud**. The whole git repo is cloned into
  `apps/illumenate_lighting` on the bench; the installable Python package is the
  inner `illumenate_lighting/` folder (flit build).
- Python package root: `illumenate_lighting/illumenate_lighting/` contains `api/`,
  `doctype/`, `portal/`, `page/`. Hooks: `illumenate_lighting/hooks.py`.
- Web pages: `illumenate_lighting/templates/pages/<name>.py` + `<name>.html`, mapped to
  URLs by `website_route_rules` in `hooks.py` (around line 88), e.g.
  `{"from_route": "/portal/product-finder", "to_route": "product_finder"}`.
- Static assets: `illumenate_lighting/public/**` is served at
  `/assets/illumenate_lighting/**` **without authentication**. Never put site data there.
- Python style: **tabs** for indentation, ruff (`ruff check .`, `ruff format .`),
  line length 110, `from __future__ import annotations` is common. Match the
  surrounding file. JS/JSX in the builder uses 2-space indentation.

### The builder UI (`tools/yaml_builder_ui`)

- `src/main.jsx` mounts `<Workspace>` → `CatalogApp` (v2 editor) or `App` (legacy
  "family expansion" editor) into `#root`.
- `src/CatalogApp.jsx` (~300 lines): state is kept in `localStorage`
  (`STORAGE`, plus `PENDING` = `'illumenate-erp-reference-pending'`). The reference
  loads lazily at line ~157:
  `import('./erp-reference.json').then(module => setExported(module.default))`.
  `RecordFields` renders every field from the schema; Link fields get a `<datalist>`
  of catalog names + `external_links` + `reference.doctypes[target].records` keys.
  `ReferencePanel` lists existing records and offers **Copy as new record**.
  The **Download catalog** button is disabled while `catalogIssues(...)` is non-empty.
- `src/catalog-model.js`: pure helpers — `recordName`, `blankRecord`, `parseCatalog`,
  `linkedRecords`, `inReference`, `referenceSummary`, `unresolvedLinks`,
  `withReferenceLinks` (moves links that match the reference into `external_links`),
  `unconfirmedLinks`, `catalogKey`, `referenceRecord`, `catalogAddition`,
  `mergeAdditions`, `excludeCatalog`, `referenceOrigin`, `catalogIssues`, `makeItemRecords`.
- `src/catalog-schema.json`: DocType metadata snapshot generated by
  `python -m tools.fixture_builder.catalog_schema` and checked with `--check`.
- `src/catalog-examples.json`: one example catalog per product family.
- Tests: `npm test` (`node --test tests/*.test.js`, pure model tests) and
  `npm run test:render` (`tests/render.mjs`, server-renders `CatalogApp`, every example
  record, and the legacy editor). `npm run build` = schema check + `vite build`.
- `vercel.json`: Vercel build (`schema --check && npm test && vite build`), output `dist/`.

### Reference snapshot shape (`erp-reference.json`)

```json
{
  "schema_version": 1,
  "exported_on": "2026-10-04",
  "doctypes": {
    "ilL-Attribute-Finish": {
      "source": "export",            // "export" = complete list; otherwise only names other records link to
      "exported_on": "2026-10-01",
      "records": { "White": { "finish_name": "White", "code": "WH", "status": "Active" } }
    }
  },
  "catalog_additions": [ { "catalog": "...", "added_on": "...", "records": { "DocType": ["name"] } } ]
}
```

Records keep current-DocType fields only, minus audit fields, `Currency` fields,
`Item Supplier` and Webflow sync-state children; `ilL-Webflow-Product` keeps short
fields only (`SUMMARY_ONLY`, `SHORT_TYPES` in both `erp_reference.py` and
`catalog-model.js`). The snapshot (exported 2026-10-04) holds e.g. 2,331 Items,
130 Fixture Templates, 89 LED Tape specs, 11 Extrusion Kit Templates.

### The Python catalog code (`tools/fixture_builder`)

- `catalog_schema.py`: `ROOT` (repo root), `DOCTYPE_ROOT`
  (`illumenate_lighting/illumenate_lighting/doctype`), `SNAPSHOT`, `PRODUCTS`
  (product type → template/spec DocType), `standard_doctypes()` (explicit ERPNext
  subset: Item, Item Variant Attribute, Item Supplier, Item Attribute(+Value),
  Item Group, UOM, Brand, Item Price), `build_schema()` (reads every DocType JSON,
  selects `ilL-Attribute-*`, `ilL-Spec-*`, `ilL-Rel-*`, `*-Template`,
  `*-Submittal-Mapping`, Webflow Product/Category and all reachable child tables).
  No Frappe import.
- `catalog.py`: `identity()` (record name from autoname), `with_defaults()`,
  `_record_errors()`, `links()` (all Link/Dynamic Link targets incl. child rows),
  `_variant_errors()`, **`prepare_catalog(config, schema, reference)`** → returns
  `(records, batches, used_external)` where `batches` is an ordered list of
  `(doctype, [records])` ready for insertion in dependency order, and raises
  `ValueError("\n".join(errors))` on any problem. `reference` is `{doctype: set(names)}`.
  `csv_data()` and `generate_catalog()` write CSVs/manifest. It already imports
  `illumenate_lighting.illumenate_lighting.api.authoring_contract.record_issues`
  (pure engineering checks; no Frappe import).
- `erp_reference.py`: builds/loads the snapshot. `load_reference(path, config)` →
  `{doctype: set(names)}`; `unconfirmed_links()`; `add_catalog()`; imports `identity`
  from `.catalog` and `ROOT`, `build_schema` from `.catalog_schema`.
- `__main__.py`: CLI (`--config`, `--output`, `--reference`, `--no-reference`, legacy modes).
- Tests: `python -m unittest discover -s tools/fixture_builder/tests -q` (132 tests,
  all passing on 2026-10-05) — `test_catalog.py`, `test_catalog_legacy.py`,
  `test_erp_reference.py`, `test_generators.py`, `test_tape_neon_generators.py`.

### Precedent to copy: the Product Finder

The Product Finder is a React app built by Vite into a **single IIFE bundle**,
**committed** to `illumenate_lighting/public/product_finder/<mode>/`, and served by a
login-guarded web page:

- `tools/configurator_ui/vite.config.js` — `finderBuild(mode)`: `base`
  `/assets/illumenate_lighting/product_finder/${mode}/`, `build.lib` with
  `formats: ['iife']`, `name: 'IllFinderBundle'`, `fileName: () => 'ill-finder.js'`,
  `cssCodeSplit: false`, `assetFileNames: 'ill-finder.[ext]'`,
  `define: {'process.env.NODE_ENV': '"production"'}`, `outDir` into `public/`.
- `illumenate_lighting/templates/pages/product_finder.py` — redirects `Guest` to
  `/login?redirect-to=...` via `frappe.local.flags.redirect_location` +
  `raise frappe.Redirect`, checks permission, passes
  `csrf_token = frappe.sessions.get_csrf_token()` into the context.
- `product_finder.html` — loads the CSS/JS from `/assets/...` and calls
  `IllConfigurator.mount('<root id>', {csrfToken: ..., ...})`.
- CI (`.github/workflows/b2b-contracts.yml`, step "Product Finder bundles are fresh")
  rebuilds and runs `git diff --exit-code illumenate_lighting/public/product_finder`.

### Permissions and API conventions

- Staff capabilities: `illumenate_lighting/illumenate_lighting/portal/staff.py`.
  `CAPABILITIES["catalog"] = {"ilL Catalog Publisher"}`; `allowed(capability)` is
  true for Administrator and for enabled **System Users** holding a capability role
  or `System Manager`; `require(capability)` throws `frappe.PermissionError`.
- Endpoint style (see `api/publication.py`):
  ```python
  @frappe.whitelist(methods=["POST"])
  def inspect(product, brand):
  	require_catalog_reader()
  	...
  ```
  Use `methods=["GET"]` for reads. Client calls go to `/api/method/<dotted.path>`
  with header `X-Frappe-CSRF-Token` for POSTs (same-origin cookies authenticate).
- Unit tests without a Frappe bench: `tests/portal_unit/test_services.py` provides
  `load_service(relative, extras)`, which installs a fake `frappe` module
  (`MagicMock`s for `db`, `get_doc`, `get_all`, `get_roles`, ...). CI runs
  `python -B -m unittest discover -s tests/portal_unit`. Real Frappe tests run in
  `.github/workflows/ci.yml` (MariaDB + bench, v16).
- `doc_events` in `hooks.py`: attribute DocTypes and Webflow Product have
  `after_insert`/`on_update` hooks (`api/webflow_sync_events.py`) that **only write DB
  flags** (`frappe.db.set_value(... "Pending")`) and call `frappe.log_error` on
  failure; they do not call Webflow or enqueue jobs. Webflow Product updates also call
  `publication.invalidate_product`.

### CI checks to keep green

- `b2b-contracts.yml`: `unittest` for `tests/portal_unit` and `tools/fixture_builder/tests`;
  `tools/check_portal_templates.py` (parses every `templates/**/*.html` with Jinja and
  renders some with stubs; a stub `templates/web.html` is provided); Product Finder
  bundle freshness; `tools/check_b2b_changes.py` (changed-file lint and schemas).
- `ci.yml`: Frappe v16 server tests.
- `linter.yml`: ruff/pre-commit.

## 2. Assumptions and decisions (confirm with the owner before Session 1)

| Variable | Assumed value | Notes |
|---|---|---|
| Production site URL | `<PROD_SITE>` (Frappe Cloud) | Fill in. |
| Staging site URL | `<STAGING_SITE>` | Repo has a `staging` branch that CI runs on; confirm a staging site is deployed from it. |
| Page URL | `/catalog-builder` | Route rule → `templates/pages/catalog_builder`. |
| Who may open it | `staff.allowed("catalog")` → `ilL Catalog Publisher`, `System Manager`, Administrator | Open question: add a separate `ilL Catalog Author` role for people who may Check but not Import? Default: one role for both. |
| ERPNext create permissions | Imports run **with normal user permissions** (no `ignore_permissions`) | The role must have Create on every DocType a catalog can contain (Item, all `ilL-Spec-*`, `ilL-Rel-*`, templates, Webflow Product, attributes). Verify in Role Permissions Manager in Session 5. |
| Vercel deployment | Keep running during Sessions 1–4; decide in Session 5 | Vercel stays snapshot-based (the static build keeps working). |
| Max catalog size per import | 500 records (configurable constant) | Frappe Cloud web workers time out around 120 s; typical catalogs are 10–50 records. Background jobs are a follow-up if needed. |
| Default company | The site's default company is set | ERPNext Item insert fills Item Defaults from it. |
| Attachments (`Attach`, `Attach Image` fields) | Out of scope: values must be existing file URLs | Upload UI is a follow-up. |
| Updates to existing records | Out of scope: insert-only, as today | |
| Transaction model | One DB transaction per Import; rollback on any error | Verify no hook commits mid-request (Session 5). |

## 3. Ground rules for every session

- Work on a feature branch; one PR per session. Keep diffs scoped to the session.
- Before pushing: `ruff check .`, `ruff format --check` on touched files,
  `python -m unittest discover -s tools/fixture_builder/tests -q`,
  `python -B -m unittest discover -s tests/portal_unit`,
  `python -B tools/check_portal_templates.py`, and in `tools/yaml_builder_ui`:
  `npm ci && npm test && npm run test:render && npm run build`.
- Never put site data or secrets under `illumenate_lighting/public/` (served publicly).
- The Vercel build and the CLI must keep working after every session.
- Built bundles are committed (like the Product Finder) and CI checks they are fresh.
- Update `tools/yaml_builder_ui/README.md` and `tools/fixture_builder/CATALOG.md`
  when behaviour changes. Write in the existing terse style.

---

## Session 1 — Host the builder inside ERPNext

**Goal:** the existing builder runs at `/catalog-builder` on the ERPNext site for
logged-in catalog staff, with the reference snapshot delivered by an authenticated
endpoint instead of the bundle. No behaviour change in the editor itself.

### Read first

`tools/yaml_builder_ui/src/main.jsx`, `src/CatalogApp.jsx` (lines 143–175),
`vite.config.js`, `package.json`, `vercel.json`;
`tools/configurator_ui/vite.config.js`, `vite.portal.config.js`;
`illumenate_lighting/templates/pages/product_finder.py` and `.html`;
`illumenate_lighting/hooks.py` (`website_route_rules`);
`illumenate_lighting/illumenate_lighting/portal/staff.py`;
`.github/workflows/b2b-contracts.yml`; `tools/check_portal_templates.py`.

### Steps

1. **Make the reference source injectable.** In `CatalogApp.jsx`, accept a prop
   `loadReference` (default: `() => import('./erp-reference.json').then(m => m.default)`)
   and call it in the `useEffect` at line ~157. Keep the Vercel behaviour identical.
   Thread it through `Workspace` in `main.jsx`.
2. **ERP entry point.** Add `src/erp-main.jsx` exporting
   `mount(elementId, {csrfToken, referenceUrl})` that renders the same `Workspace`
   with `loadReference = () => fetch(referenceUrl, {credentials: 'same-origin'})
   .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(r => r.message)`.
   Expose it as a global (e.g. `window.IllCatalogBuilder = { mount }` via the IIFE
   `name`). It must **not** statically or dynamically import `erp-reference.json`
   (an IIFE build inlines dynamic imports, adding 4.3 MB).
3. **Second Vite config** `tools/yaml_builder_ui/vite.erp.config.js` modelled on
   `finderBuild`: `base: '/assets/illumenate_lighting/catalog_builder/'`,
   `outDir: '../../illumenate_lighting/public/catalog_builder'`, `emptyOutDir: true`,
   `lib: {entry: 'src/erp-main.jsx', name: 'IllCatalogBuilder', formats: ['iife'],
   fileName: () => 'catalog-builder.js'}`, `cssCodeSplit: false`,
   `assetFileNames: 'catalog-builder.[ext]'`, `define` NODE_ENV production.
   Add `"build:erp": "npm run schema:check && vite build --config vite.erp.config.js"`
   to `package.json`. Do **not** change `vercel.json` or the default `build`.
   Confirm the output contains no reference data
   (`grep -c '"exported_on"' illumenate_lighting/public/catalog_builder/catalog-builder.js` → 0)
   and note its size (expect < 1 MB; the schema JSON is ~170 KB and is fine to inline).
4. **Reference endpoint.** New module
   `illumenate_lighting/illumenate_lighting/api/catalog_builder.py`:
   ```python
   @frappe.whitelist(methods=["GET"])
   def reference():
   	require("catalog")            # from ..portal.staff
   	return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
   ```
   `SNAPSHOT_PATH = Path(frappe.get_app_path("illumenate_lighting")).parent / "tools/yaml_builder_ui/src/erp-reference.json"`.
   (The full repo is present on Frappe Cloud benches; verify on staging. If it is not,
   fall back to Session 2's live builder early.) Return `{"doctypes": {}, ...}` with a
   clear message if the file is missing rather than a 500.
5. **Page.** `illumenate_lighting/templates/pages/catalog_builder.py`:
   - `no_cache = 1`
   - `Guest` → redirect to `/login?redirect-to=/catalog-builder` (copy the product_finder pattern).
   - Not `staff.allowed("catalog")` → `frappe.throw(_("Catalog staff access is required"), frappe.PermissionError)`
     (or redirect to `/app` with a message).
   - Context: `csrf_token`, `reference_url = "/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.reference"`,
     `asset_version` (e.g. file mtime or a hash) for cache-busting `?v=`.
   `catalog_builder.html`: a **standalone** HTML document (`<!doctype html>`, own
   `<head>`, no `{% extends "templates/web.html" %}`) because Tailwind's `@tailwind base`
   reset would restyle the website chrome. Load
   `/assets/illumenate_lighting/catalog_builder/catalog-builder.css?v=...` and `.js`,
   then `IllCatalogBuilder.mount('catalog-builder-root', {csrfToken: {{ csrf_token|tojson }}, referenceUrl: {{ reference_url|tojson }}})`.
   **Verify** that Frappe v16 renders a template without `extends` as-is (Frappe wraps
   templates that lack `<html` in the base template; a full document should be left
   alone). If it still wraps, extend a minimal base or set `base_template_path` in context.
6. **Route.** Add `{"from_route": "/catalog-builder", "to_route": "catalog_builder"}` to
   `website_route_rules` in `hooks.py`.
7. **Desk shortcut (optional).** Add a link to `/catalog-builder` on an existing
   workspace used by catalog staff (`illumenate_lighting/illumenate_lighting/workspace/illumenate_lighting/`
   ) — a URL shortcut, not a Desk Page.
8. **CI.** In `b2b-contracts.yml` add a step "Catalog Builder bundle is fresh":
   `npm ci --prefix tools/yaml_builder_ui`, `npm test --prefix tools/yaml_builder_ui`,
   `npm run build:erp --prefix tools/yaml_builder_ui`,
   `git diff --exit-code illumenate_lighting/public/catalog_builder`.
   Make sure `tools/check_portal_templates.py` parses the new template (it parses every
   `templates/**/*.html`; add a render case with stub context if other pages have one).
9. **Tests.**
   - `tests/portal_unit/test_catalog_builder.py` using `load_service`: `reference()`
     rejects Guest and non-catalog users (`frappe.get_roles` → `["Dealer"]`), returns
     the snapshot dict for a catalog user; page `get_context` redirects Guest.
   - `tests/render.mjs`: also render with a `loadReference` prop to prove injection works.
10. **Docs.** README section "Use the builder in ERPNext": URL, role, drafts are per
    site (move them with **Save draft** / **Open YAML**), Vercel still available.

### Acceptance

- `/catalog-builder` on a local bench or staging: Guest → login → back to the builder;
  a user without the role is refused; a catalog user sees the editor, link suggestions
  show "Existing ERPNext record", **Download catalog** works.
- Browser network tab: the JS bundle contains no reference data; the reference comes
  from `/api/method/...reference` with the session cookie.
- Vercel build unchanged (`npm run build` still produces `dist/` with the lazy chunk).
- All CI checks above pass.

### Out of scope

Live data, import, any change to `catalog-model.js` logic.

---

## Session 2 — Live ERPNext data instead of the snapshot

**Goal:** in ERP mode the builder's "existing records" come from the live site at page
load (and on **Refresh**), so no export/snapshot step is ever needed there. The snapshot
and `add_to_reference` keep working for Vercel/CLI users.

### Read first

`tools/fixture_builder/erp_reference.py` (whole file: field filtering rules,
`reference_record`, `_linked`, `build_reference`), `catalog_schema.py`,
`src/catalog-model.js` (`inReference`, `referenceSummary`, `referenceRecord`,
`unconfirmedLinks`, `mergeAdditions`, `excludeCatalog`), `src/CatalogApp.jsx`
(`ReferencePanel`, add-to-reference checkbox, `PENDING` handling), and Session 1's
`api/catalog_builder.py`.

### Steps

1. **Live reference builder** in `api/catalog_builder.py`:
   `live_reference()` returns the **same JSON shape** as the snapshot with
   `"source": "live"` per DocType and `"exported_on"` = now (ISO):
   - DocTypes: every parent DocType in `build_schema()["doctypes"]` (non-`istable`) —
     about 65 — including Item, Item Group, UOM, Brand, Item Attribute.
   - Per DocType, one `frappe.get_all(doctype, fields=[...], limit_page_length=0)`
     selecting only **short fields** (`SHORT_TYPES` = Data, Link, Dynamic Link, Select,
     Int, Float, Check) that exist in the live meta (`frappe.get_meta(doctype).has_field`)
     — skip `Currency`, audit fields and Webflow sync fields exactly as `erp_reference.py` does.
     No child tables in the list payload.
   - Skip DocTypes the user cannot read (`frappe.has_permission(doctype, "read")`);
     report them in a `"skipped"` list so the UI can say so.
   - Cache per site in `frappe.cache()` for ~5 minutes (key includes a version stamp);
     `refresh=1` bypasses the cache. Target: < 3 s uncached, payload < 2 MB.
   - Make `reference()` call `live_reference()` (keep the file-snapshot path only as a
     fallback flag if useful, or delete it).
2. **Full record on demand.** `@frappe.whitelist(methods=["GET"]) def record(doctype, name)`:
   `require("catalog")`, check `doctype` is in the authorable schema, `frappe.get_doc(...)`
   with read permission, return `as_dict()` reduced to schema fields (+ child tables,
   same filtering rules). Used by **Copy as new record**.
3. **UI changes (ERP mode only; pass a `mode: 'erp'` prop from `erp-main.jsx`):**
   - Treat `source: 'live'` as complete (like `'export'`) wherever `catalog-model.js`
     or `ReferencePanel` distinguishes partial lists; label it
     "Live from ERPNext · loaded HH:MM" instead of "export of <date>".
   - Add a **Refresh ERPNext records** button that refetches with `refresh=1`.
   - **Copy as new record** in `ReferencePanel`: in ERP mode fetch the full record via
     `record()` before copying (the live list has no child tables).
   - Hide the **Add to ERPNext reference after import** checkbox and ignore `PENDING`
     additions in ERP mode (the live site is the reference). Leave Vercel mode untouched.
   - Datalist size: Item has ~2,300 names; a `<datalist>` handles this, but if typing
     lags, switch Item (and any DocType > 1,000 records) to server search via
     `/api/method/frappe.desk.search.search_link?doctype=Item&txt=<q>&page_length=20`
     with a 200 ms debounce. Measure before adding complexity.
4. **Keep the CLI/snapshot path.** No change to `erp_reference.py` behaviour. Optional
   nicety: add `--from-site` later; not in this session.
5. **Tests.**
   - `tests/portal_unit/test_catalog_builder.py`: `live_reference()` with mocked
     `frappe.get_all`/`get_meta`/`has_permission`: shape matches the snapshot schema,
     currency/audit fields dropped, unreadable DocTypes listed in `skipped`, permission gate.
   - `tests/catalog.test.js`: model helpers treat `'live'` as complete.
   - `render.mjs`: render ERP mode (no add-to-reference checkbox, Refresh button present).
6. **Docs.** README: in ERPNext the records are live; snapshot only for Vercel/CLI.

### Acceptance

- Create a test attribute value in ERPNext Desk, click **Refresh** in the builder: it
  appears as an existing record without any export.
- Copy-as-new on an existing `ilL-Rel-Profile Lens` brings its `compatible_lenses` rows.
- Vercel build still loads the snapshot.

### Out of scope

Import, Check, server-side validation.

---

## Session 3 — Server import engine (Check and Import endpoints)

**Goal:** a server API that takes a catalog (the same JSON the builder produces),
validates it against the live site, and either dry-runs (Check) or inserts it (Import)
in one transaction, returning per-record results. Logged in a new DocType.

### Read first

`tools/fixture_builder/catalog.py` (all), `catalog_schema.py` (all),
`erp_reference.py` (imports only), `__main__.py` (how `generate_catalog` and
`load_reference` are called), `tools/fixture_builder/tests/test_catalog.py`,
`api/authoring_contract.py`, `portal/staff.py`, `api/publication.py` (endpoint and
locking style), an existing simple log DocType such as
`illumenate_lighting/illumenate_lighting/doctype/ill_export_job/` (JSON + .py layout).

### Step 3.1 — Move the shared catalog code into the app package

The CLI lives in `tools/`, which is **not** part of the installed Python package, so the
server cannot import it reliably. Move the pure logic into the app and leave thin
re-exports so nothing else changes:

- New package `illumenate_lighting/illumenate_lighting/catalog_authoring/` with
  `__init__.py`, `schema.py` (contents of `catalog_schema.py` minus the CLI `main()` and
  `SNAPSHOT`; `DOCTYPE_ROOT = Path(__file__).resolve().parents[1] / "doctype"`) and
  `catalog.py` (everything in `tools/fixture_builder/catalog.py` **except** file writing:
  keep `identity`, `with_defaults`, `links`, `prepare_catalog`, `csv_data`, constants).
- `tools/fixture_builder/catalog_schema.py` → `from illumenate_lighting.illumenate_lighting.catalog_authoring.schema import *`
  plus `ROOT`, `SNAPSHOT` and `main()` (snapshot writing/checking stays in tools).
- `tools/fixture_builder/catalog.py` → re-export from the app module and keep
  `generate_catalog()` (file writing) there.
- **No `import frappe` anywhere in `catalog_authoring/`** — the CLI and its unit tests
  run without Frappe.
- All 132 existing fixture_builder tests must pass unchanged; `catalog_schema --check`
  must still pass (the generated JSON must be byte-identical).

### Step 3.2 — Log DocType `ilL-Catalog-Import`

Create via JSON (module `ilLumenate Lighting`, same as other DocTypes, e.g. `doctype/ill_export_job/`;
`autoname: "hash"` or `format:CAT-IMP-{#####}`), not submittable, track_changes off:

| Field | Type | Notes |
|---|---|---|
| `mode` | Select `Check\nImport` | |
| `status` | Select `Running\nPassed\nFailed\nImported\nRolled Back` | |
| `product_type` | Data | |
| `series_name` | Data | |
| `catalog_hash` | Data | sha256 of canonical JSON (`json.dumps(sort_keys=True)`) |
| `catalog_json` | Long Text / JSON | the submitted catalog |
| `results_json` | JSON | per-record results (below) |
| `error_count`, `warning_count`, `record_count` | Int | |
| `duration_ms` | Int | |

Permissions: read for `ilL Catalog Publisher` and `System Manager`; create/write only via
the endpoint (`ignore_permissions` **only** for this log insert). Add it to whatever
fixture/patch mechanism the app uses for new DocTypes (check `hooks.py` `fixtures` and
`patches.txt`).

### Step 3.3 — Endpoints in `api/catalog_builder.py`

```python
@frappe.whitelist(methods=["POST"])
def check(catalog):      # dry run
@frappe.whitelist(methods=["POST"])
def import_catalog(catalog, expected_hash=None):
@frappe.whitelist(methods=["GET"])
def history(limit=20):
```

Common pipeline (`_run(catalog, commit: bool)`):

1. `require("catalog")`. Parse `catalog` (JSON string or dict). Reject > `MAX_RECORDS` (500).
2. **Live existence map.** Collect every `(target_doctype, value)` from
   `links()` over all records plus every record's own `identity()`. For each DocType,
   one `frappe.get_all(dt, filters={"name": ["in", names]}, pluck="name")`. Build
   `reference = {dt: set(found)}`.
3. `records, batches, external = prepare_catalog(catalog, build_schema(), reference)`.
   On `ValueError`, return `{"ok": False, "stage": "validate", "errors": str(e).split("\n")}`
   without touching the DB. These are the same messages the CLI prints.
4. **Permission pre-check:** `frappe.has_permission(dt, "create")` for every DocType in
   `batches`; collect failures as errors before inserting anything.
5. **Insert.** For each `(doctype, rows)` in `batches`, for each row:
   - `frappe.local.message_log = []` (capture msgprints as warnings).
   - `frappe.db.savepoint("catalog_row")`.
   - `doc = frappe.get_doc({"doctype": doctype, **row}); doc.insert()` (normal
     permissions; **never** `ignore_permissions`, `ignore_links` or `ignore_mandatory`).
     For autoname `prompt` DocTypes pass `name` through (`doc.insert(set_name=row["name"])`
     or `doc.name = ...`; check how prepare_catalog's `identity()` expects it).
   - On exception: `frappe.db.rollback(save_point="catalog_row")`, record
     `{doctype, name, status: "error", message: <cleaned exception text>}`, add `(doctype, name)`
     to a `failed` set, and **continue** so the user sees every problem at once.
   - Rows whose dependencies (via `links()`) include a failed record are recorded as
     `status: "skipped", message: "Depends on <doctype> <name>, which failed"` without
     attempting insert.
   - On success: `{doctype, name: doc.name, status: "created" | "checked", warnings: [...]}`
     where warnings come from `frappe.local.message_log` (strip HTML).
6. **Finish.**
   - Check mode, or Import with any error/skip: `frappe.db.rollback()`.
   - Import with zero errors: let the request commit (Frappe commits successful POSTs)
     — or `frappe.db.commit()` explicitly, then write the log.
   - Write the `ilL-Catalog-Import` log **after** the rollback/commit and commit it, so
     a rolled-back import still leaves an audit row.
7. Return `{"ok", "mode", "log": <name>, "catalog_hash", "summary": {created, checked,
   errors, skipped, warnings}, "results": [...], "external": [[dt, name], ...]}`.

`import_catalog(expected_hash)`: if provided, refuse when it differs from the hash of the
submitted catalog (protects against importing something other than what was checked).
Optionally require a passing Check log with the same hash within the last 30 minutes.

Concurrency: take a lock so two imports cannot run at once
(`frappe.cache().set_value("catalog_import_lock", ..., expires_in_sec=300)` or a DB
`select ... for update` on a settings row). Simple is fine.

`history()`: last N logs for the current user (or all, for System Manager): name,
mode, status, series, counts, creation.

### Step 3.4 — Tests

- `tools/fixture_builder/tests`: unchanged and green (proves the move is behaviour-neutral).
- `tests/portal_unit/test_catalog_import.py` with `load_service` mocks:
  validation errors short-circuit before any `get_doc`; batches inserted in order;
  one failing row → later dependents `skipped`, unrelated rows still `checked`;
  Check always rolls back; Import with an error rolls back; Import success commits;
  log written after rollback; permission gate; `MAX_RECORDS`; hash mismatch refused.
- Bench test (runs in `ci.yml`): `illumenate_lighting/illumenate_lighting/doctype/ill_catalog_import/test_ill_catalog_import.py`
  (or `api/test_catalog_builder.py`) importing the **extrusion-kit** example catalog
  (`tools/fixture_builder/templates/catalog_extrusion-kit.yaml`) after creating its
  `external_links` records in setup; assert records exist after Import and do not after Check.
  Look at an existing bench test for fixture/setup conventions.

### Acceptance

- `curl`/Postman against a local bench: Check on the extrusion-kit example returns
  per-record `checked` with zero rows left in the DB; Import creates them all; a
  deliberately broken row (e.g. unknown `lens_spec`) makes Import roll back everything
  and report the row plus its skipped dependents.
- CLI output unchanged for every `templates/catalog_*.yaml`.

### Known risks to note in the PR

- Some ERPNext core hooks might commit; Session 5 verifies on staging.
- `frappe.log_error` inside hooks writes Error Log rows; harmless.
- Item insert depends on site defaults (company, Stock Settings); errors will surface
  per row, which is the point.

---

## Session 4 — Import UI in the builder

**Goal:** in ERP mode, staff can Check and Import from the builder and read the results.

### Read first

`src/CatalogApp.jsx` (header actions, `catalog-review` aside, `message`/`confirm`
patterns), `src/catalog.css`, Session 3's endpoint contract, `erp-main.jsx`.

### Steps

1. **API client** `src/erp-api.js`: `post(method, args)` → `fetch('/api/method/' + method,
   {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json',
   'X-Frappe-CSRF-Token': csrfToken}, body: JSON.stringify(args)})`; unwrap `message`;
   turn Frappe errors (`exc_type`, `_server_messages` JSON-in-JSON) into readable text.
   Handle 403 (session expired → "Log in again" link to `/login?redirect-to=/catalog-builder`).
2. **Catalog payload:** send `withReferenceLinks(catalog, schema, reference)` (the same
   object the YAML download contains) as JSON. Compute its hash client-side
   (SubtleCrypto sha256 over the same canonical JSON as the server — or simply use the
   hash the Check response returns and pass it back as `expected_hash`).
3. **Buttons (ERP mode only)** next to **Download catalog**:
   - **Check in ERPNext** — enabled when browser `issues` is empty. Shows a spinner;
     disables editing actions while running.
   - **Import to ERPNext** — enabled only after a passing Check **of the current
     catalog** (hash matches; any edit invalidates it). Confirmation dialog listing
     counts per DocType ("Create 5 Items, 1 Extrusion Kit Template, 4 maps…").
4. **Results panel** (replace or extend the right-hand `catalog-review` aside, or a
   full-width section below the editor):
   - Summary line: created / checked / errors / skipped / warnings, duration.
   - Table grouped in batch order: DocType, record name (link to
     `/app/<doctype-slug>/<name>` after Import; slug = `doctype.toLowerCase().replace(/ /g, '-')`),
     status pill, message/warnings.
   - Clicking an error selects that DocType/record in the editor where possible
     (match by `recordName`).
   - "Rolled back — nothing was saved" banner when applicable.
5. **After a successful Import:** clear the Check state, trigger the Session 2 reference
   refresh (new records become "existing"), and offer "Start a new draft" (the current
   draft's records now exist, so re-checking would report duplicates — say so).
6. **History:** a small "Recent imports" list from `history()` with links to the
   `ilL-Catalog-Import` log in Desk.
7. **Tests.** `render.mjs`: render results panel with a fixture response (errors,
   skipped, created). `tests/catalog.test.js`: Frappe error unwrapping, hash
   invalidation on edit (pure helper). Rebuild and commit the ERP bundle.
8. **Docs.** README section "Check and import in ERPNext" (what Check proves, that Import
   is all-or-nothing, that publication is still separate, insert-only limitation).

### Acceptance

- On a local bench/staging: load the extrusion-kit example, fix its placeholder
  attribute names (see Session 5 note), Check → all `checked`; edit a field → Import
  disabled until re-Check; Import → records linked and openable in Desk; history shows
  both runs; a broken catalog shows the errors and "nothing was saved".

---

## Session 5 — Staging rehearsal and hardening

**Goal:** prove the end-to-end flow on the real staging site for every product family,
fix what breaks, and decide the Vercel deployment's future.

### Steps

1. Deploy the branch to `<STAGING_SITE>` (Frappe Cloud: push to the branch the staging
   bench tracks, then **Update** the bench; run `bench migrate` if the bench does not).
   Confirm `/catalog-builder` loads and the bundle version is current.
2. **Role setup:** assign `ilL Catalog Publisher` to a non-admin test user; in Role
   Permissions Manager grant Create/Read/Write on every DocType the import touches.
   Record the final permission list in `docs/B2B_STAFF_OPERATIONS.md` (or a new section
   in the builder README).
3. **Example catalogs need real names.** The shipped examples
   (`tools/fixture_builder/templates/catalog_*.yaml`, `src/catalog-examples.json`) use
   placeholder values that do **not** exist on the live site, e.g.
   `ilL-Attribute-Endcap Color: White` (site has `WH`/`BK`/`GR`), `CRI: 90` (site: `90+`/`95+`),
   `Output Voltage: 24V DC` (site: `24VDC`), `LED Package: SW` (site: `ilLumenate Static White`, …),
   `Power Feed Type: Single End Feed` (site: `Soldered-End`), `ilL-Spec-Driver: EXISTING-96W-DRIVER`.
   For the rehearsal, build one realistic catalog per family by **linking to real
   records** (e.g. extrusion kit `KIT-CA01` for the Castle CA01 profile family — the
   site has profiles `CH-CA01-WH/BK/SV`, lenses `LNS-CAXX-WH-{WH,FR,CL,BK}`, endcaps
   `EC-CA01-{WH,BK,GR}-{NO,HO}`, mounting `ACC-CAXX-MC`, `ACC-CA01-PV` and existing
   `KIT-CA01*` Items, but no `ilL-Extrusion-Kit-Template` named `KIT-CA01`). Consider a
   separate PR updating the examples to real names.
4. **Rehearse per family** (fixture, tape, neon, LED sheet, extrusion kit, driver,
   controller): Check → Import → open each created record in Desk → open the product
   in the relevant configurator (portal `/portal/configure/<template>`,
   `/portal/configure-tape`, `/portal/configure-sheet`, desk kit configurator) and
   confirm it resolves. Then delete the test records (or use clearly named
   `ZZ-TEST-*` series) — note delete order is the reverse of the batch order.
5. **Transaction proof:** import a catalog whose last batch fails; confirm in Desk that
   *none* of the earlier records exist. If any do, find the committing hook (search
   ERPNext/app code for `frappe.db.commit` reached from `Item`/`ilL-*` insert paths)
   and handle it (e.g. `frappe.flags.in_import = True`, or split into per-DocType
   savepoints with compensating deletes — document the choice).
6. **Timing:** time Check/Import on the largest realistic catalog (e.g. a fixture
   family with ~50 records). If > 60 s, move `_run` to `frappe.enqueue(queue="long")`
   with the log DocType as the status record and poll it from the UI.
7. **Security review:** endpoints refuse Guest, dealers and System Users without the
   role; CSRF required for POSTs; no site data under `public/`; catalog JSON size
   capped (request body limit); `doctype` argument of `record()` restricted to the schema.
8. **Decide Vercel:** (a) retire it — delete the Vercel project, keep `vercel.json` or
   remove it and the README section; or (b) keep it as an offline drafting tool with the
   snapshot. Record the decision in the README.
9. **Docs:** update `tools/yaml_builder_ui/README.md`, `tools/fixture_builder/CATALOG.md`
   (server import behaviour, all-or-nothing, insert-only, attachments manual), and add a
   short operator checklist to `docs/B2B_STAFF_OPERATIONS.md`.
10. Promote to production via the normal `staging` → `main` release PR.

### Acceptance

Every family imported on staging from the builder with no CSVs; a failing catalog
leaves no partial records; a non-catalog user cannot reach the page or endpoints;
docs updated; Vercel decision recorded.

---

## 4. Future work (not planned)

- Updating existing records from the builder (diff + merge with Desk edits).
- Attachment upload (spec sheets, images) as part of a catalog.
- Background import with realtime progress for very large catalogs.
- Using live `frappe.get_meta` (including site custom fields) instead of the repo
  DocType JSON for the browser schema.
- One-click hand-off from Import to **Readiness and Publication**.
