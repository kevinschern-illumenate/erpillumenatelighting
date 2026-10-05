# Catalog Builder in ERPNext — implementation plan

Status: **approved for implementation** (owner answers recorded 2026-10-05).
Hand-off document for an engineer or coding agent with **no prior context**.

**Session 1 source-review correction (applied in §7.4):** the original plan said `frappe.get_all` applies row-level user
permissions. The installed Frappe v16 source explicitly sets `ignore_permissions=True`
in `get_all`. Session 2 uses `frappe.get_list` for the user-scoped live reference
and tests that it never calls `get_all`. Session 1 serves only the role-gated snapshot;
this correction does not change its scope.

**Session 2 implementation note:** shared pure catalog logic now lives in
`illumenate_lighting/illumenate_lighting/catalog_authoring/`; the CLI re-exports it.
The live picker uses `get_list`, filters field permissions, and full copies apply
`apply_fieldlevel_read_permissions()` before reduction. ERP drafts preserve but
ignore `add_to_reference`. Session 2 was branched from Session 1 while its PR was
open; merge Session 1 first, then retarget the Session 2 PR to `main`.
Local Frappe v16 verification used 2,331 synthetic Items: uncached reference 0.088 s,
JSON 511,327 bytes, and Chromium datalist keydown-to-next-frame latency 37.5 ms
median / 47.2 ms p95 over 30 keystrokes. Keep the datalist; production/staging
measurement remains part of Session 5.

## How to use this document

- Do the sessions **in order**. Each session is one branch and one pull request,
  merged before the next session starts. Every session section is self-contained:
  goal, starting-state check, files to read, steps (with code skeletons), tests,
  verification commands, deploy notes, acceptance criteria, PR checklist.
- Read sections 1–5 once before Session 1. They hold the facts every session relies
  on. Everything in them was checked against the repository and the Frappe v16
  source on 2026-10-05; line numbers drift, so search by name if a number is off.
- Code skeletons show **shape and intent**, not final code. Match the surrounding
  file's style (tabs in Python, 2 spaces in JSX).
- When something in the repository contradicts this plan, the repository wins.
  Note the difference in the PR description. Stop and ask the owner only for the
  items listed under "Ask the owner" in a session.
- Do not widen scope. "Out of scope" lists are binding.

## Contents

0. Goal and background
1. Owner decisions (final)
2. Repository facts
3. Verified Frappe v16 behaviour this plan relies on
4. Glossary
5. Ground rules, local setup and commands
6. Session 1 — Host the builder inside ERPNext
7. Session 2 — Shared catalog code in the app + live ERPNext data
8. Session 3 — Server Check/Import engine, audit log, permissions
9. Session 4 — Check/Import UI
10. Session 5 — Staging rehearsal, production rollout, Vercel decision
11. Appendix A — API contract
12. Appendix B — Troubleshooting
13. Appendix C — Future work

---

## 0. Goal and background

### What exists today

The **YAML Builder** (`tools/yaml_builder_ui`, React 18 + Vite 6 + Tailwind 3) is a
static web app hosted on Vercel. Staff use it to author product catalogs for seven
families: linear fixtures, LED tape, LED neon, LED sheets, extrusion kits, drivers
and controllers. A catalog is a "version 2" YAML/JSON document:

```yaml
schema_version: 2
product_type: extrusion-kit        # fixture | tape | neon | led-sheet | extrusion-kit | driver | controller
series_name: Castle
records:                           # {DocType: [record, ...]}; keys are DocType fieldnames
  ilL-Extrusion-Kit-Template:
    - template_code: KIT-CA01
      template_name: Castle CA01 Extrusion Kit
      allowed_options:             # child tables are lists of mappings
        - {option_type: Finish, finish: White, is_active: 1}
external_links:                    # records that already exist in ERPNext: {DocType: [names]}
  ilL-Attribute-Finish: [White]
add_to_reference: true             # optional; snapshot workflow only
```

A Python CLI validates the catalog and writes numbered ERPNext Data Import CSVs:

```
python -m tools.fixture_builder --config my.yaml --output ./output/my/
```

Staff then import each CSV by hand through ERPNext **Data Import** ("Insert New
Records"), in manifest order. Links to records that already exist in ERPNext are
resolved against a **committed snapshot**, `tools/yaml_builder_ui/src/erp-reference.json`
(~4.3 MB), rebuilt from manual DocType exports
(`python -m tools.fixture_builder.erp_reference <exports.zip>`).

Read these short, current docs first: `tools/yaml_builder_ui/README.md`,
`tools/fixture_builder/README.md`, `tools/fixture_builder/CATALOG.md`.

### Target workflow (end of Session 5)

1. Catalog staff open **https://illumenatelighting.v.frappe.cloud/catalog-builder**,
   logged in with their normal ERPNext account (no separate login, no API keys).
2. Link fields suggest **live** ERPNext records. No snapshot, no exports.
3. **Check in ERPNext** runs a full server-side dry run: every record is inserted with
   all ERPNext validation, then everything is rolled back. Errors and warnings are
   listed per record.
4. **Import to ERPNext** (available only right after a passing Check of the exact same
   catalog) inserts every record in dependency order **in one transaction**. Any
   failure rolls back everything. A results table links each created record in Desk.
5. Every Check and Import is recorded in an audit DocType, `ilL-Catalog-Import`.

Publishing to Webflow stays a separate, deliberate step through the existing
**Readiness and Publication** flow (`docs/B2B_PUBLICATION_RUNBOOK.md`). Importing
never publishes, prices orders, or syncs anything.

### Session map

| # | Session | Delivers | Deploy type | Depends on |
|---|---|---|---|---|
| 1 | Host the builder inside ERPNext | `/catalog-builder` page, login and role gate, snapshot served by an authenticated endpoint, Desk shortcut | **Migrate** (hooks.py, workspace JSON) | — |
| 2 | Shared code + live data | Catalog code moved into the app package; live reference from the site; Refresh; full-record copy | Pull | 1 |
| 3 | Server engine | `check` / `import_catalog` / `history` endpoints, `ilL-Catalog-Import` DocType, Catalog Publisher permissions patch | **Migrate** (DocType JSON, patches.txt) | 2 |
| 4 | Import UI | Check / Import buttons, results panel, history | Pull | 3 |
| 5 | Rehearsal and rollout | Every family imported on staging, fixes, docs, production rollout, Vercel decision | per fixes | 1–4 |

"Pull" and "Migrate" are Frappe Cloud update types; see §2.8.

---

## 1. Owner decisions (final)

| Topic | Decision |
|---|---|
| Production site | `illumenatelighting.v.frappe.cloud` |
| Staging site | `stagingillumenate.v.frappe.cloud` (owner-supplied). **Note:** the repo elsewhere references `stagingillumenatelighting.v.frappe.cloud` (`illumenate_lighting/illumenate_lighting/utils.py` `ALLOWED_ORIGINS`, `docs/DEPLOYMENT_RECOVERY_PLAN_2026_09_29.md`). This feature is same-origin and does not need CORS, so do **not** edit `ALLOWED_ORIGINS`. In Session 5, open the owner-supplied URL first; if it does not resolve, try the other and confirm with the owner. |
| Page URL | `/catalog-builder` |
| Who may use it | One role for both Check and Import: **`ilL Catalog Publisher`**, plus `System Manager` and `Administrator` (this is exactly `staff.allowed("catalog")`). |
| Permissions | Imports run with the **user's own ERPNext permissions** (never `ignore_permissions` for catalog records). Session 3 grants `ilL Catalog Publisher` create/write on every DocType a catalog can contain (see §2.6 for the current gaps). |
| Size limit | **500 records** per Check/Import (counting parent records, not child rows). |
| Import gate | Import requires the `catalog_hash` of a passing Check of the identical catalog, by the same user, within the last 30 minutes. |
| Vercel | Keep it working through Sessions 1–4. Decide in Session 5 (default recommendation: keep as offline drafting tool, snapshot-based). |
| Attachments (`Attach`, `Attach Image` fields) | Out of scope. Values must be existing file URLs on the site. |
| Updating existing records | Out of scope. Insert-only, as today. |
| Transaction model | One DB transaction per run. Check always rolls back; Import commits only when every record succeeded. |

---

## 2. Repository facts

### 2.1 Layout and stack

- GitHub repo `kevinschern-illumenate/erpillumenatelighting`, default branch `main`.
  A `staging` branch feeds the staging bench (see §2.8).
- Frappe app `illumenate_lighting` for **Frappe/ERPNext v16**. Production runs Python
  3.14 (`.github/workflows/ci.yml`: `FRAPPE_BRANCH: version-16`, `PYTHON_VERSION: '3.14'`).
  `pyproject.toml`: `requires-python = ">=3.10"`, `frappe >=16.0.0-dev,<17`.
  Code must run on **3.10** (linter job), **3.11** (contracts job) and **3.14** (bench).
- Repo root contains the app package folder `illumenate_lighting/` (flit build), plus
  `tools/`, `tests/`, `docs/`, `n8n_workflows/`.
- Python package root: `illumenate_lighting/illumenate_lighting/` with `api/`,
  `doctype/`, `portal/`, `page/`, `workspace/`. App-level modules live one level up:
  `illumenate_lighting/hooks.py`, `illumenate_lighting/portal_staff_permissions.py`,
  `illumenate_lighting/portal_workspace.py`, `illumenate_lighting/patches.txt`,
  `illumenate_lighting/patches/*.py`.
- DocType module name is **`ilLumenate Lighting`** (see any DocType JSON, e.g.
  `doctype/ill_export_job/ill_export_job.json`). DocType names use the `ilL-` prefix;
  folder names are snake_case lower (`ill_export_job`), controller classes look like
  `class ilLExportJob(Document)`.
- Python style: **tabs**, ruff (`line-length = 110`, target py310, rules F, E, W, I,
  UP, B, RUF), double quotes. JS/JSX in the builder: 2-space indentation, single quotes.

### 2.2 Web pages, routes and static assets

- Web pages live in `illumenate_lighting/templates/pages/<name>.py` + `<name>.html`
  and are mapped to URLs by `website_route_rules` in `illumenate_lighting/hooks.py`
  (list starts near line 88), e.g.
  `{"from_route": "/portal/product-finder", "to_route": "product_finder"}`.
- Files in `illumenate_lighting/public/**` are served at
  `/assets/illumenate_lighting/**` **to anyone, without login**. Never put site
  data or secrets there.
- `tools/check_portal_templates.py` (CI) parses **every** `illumenate_lighting/templates/**/*.html`
  with Jinja (`StrictUndefined`) and renders some pages with stub context. It stubs
  `templates/web.html`.

### 2.3 Precedent to copy: the Product Finder bundle

The Product Finder is a React app compiled by Vite into a **single IIFE bundle**,
**committed** to `illumenate_lighting/public/product_finder/<mode>/`, and served by a
login-guarded web page.

- Build config `tools/configurator_ui/vite.config.js`:
  ```js
  export function finderBuild(mode) {
    return defineConfig({plugins:[react()], define:{'process.env.NODE_ENV':JSON.stringify('production')},
      base:`/assets/illumenate_lighting/product_finder/${mode}/`,
      build:{outDir:`../../illumenate_lighting/public/product_finder/${mode}`, emptyOutDir:true,
        lib:{entry:resolve(import.meta.dirname,'src/main.jsx'), name:'IllFinderBundle', formats:['iife'], fileName:()=> 'ill-finder.js'},
        cssCodeSplit:false, rollupOptions:{output:{assetFileNames:'ill-finder.[ext]'}}}});
  }
  ```
  `vite.portal.config.js` is `export default finderBuild('portal')`; npm scripts
  `build:portal` / `build:public`.
- Page `illumenate_lighting/templates/pages/product_finder.py`: sends `Guest` to
  `/login?redirect-to=<path>` via `frappe.local.flags.redirect_location = ...; raise frappe.Redirect`,
  checks access, and passes `csrf_token = frappe.sessions.get_csrf_token()` in context.
- `product_finder.html` extends `templates/web.html`, links
  `/assets/illumenate_lighting/product_finder/portal/ill-finder.css` and `.js`, then calls
  `IllConfigurator.mount('ill-configurator-root', {mode:'portal', csrfToken: {{ csrf_token | default('') | tojson }}, ...})`.
- CI (`.github/workflows/b2b-contracts.yml`, step "Product Finder bundles are fresh"):
  `npm ci`, `npm test`, both builds, then `git diff --exit-code illumenate_lighting/public/product_finder`.

### 2.4 The builder UI (`tools/yaml_builder_ui`)

- `package.json` scripts: `schema` / `schema:check` (run `../fixture_builder/catalog_schema.py`),
  `predev` → `schema`, `dev` → `vite`, `prebuild` → `schema:check`, `build` → `vite build`,
  `test` → `node --test tests/*.test.js`, `test:render` → `node tests/render.mjs`.
  Dependencies: react 18, react-dom 18, `yaml` 2, `lucide-react`. Dev: vite 6,
  `@vitejs/plugin-react` 4, tailwind 3, postcss, autoprefixer.
- `vite.config.js`: plain React config (dev server port 5173). `tailwind.config.js`
  content: `./index.html`, `./src/**/*.{js,jsx,ts,tsx}`. `src/index.css` starts with
  `@tailwind base; @tailwind components; @tailwind utilities;` (the base layer resets
  page-wide styles). `src/catalog.css` scopes styles under `.catalog-app`.
- `vercel.json`: `buildCommand: "python3 ../fixture_builder/catalog_schema.py --check && npm test && vite build"`,
  `outputDirectory: "dist"`, security headers (`X-Frame-Options: DENY`, etc.).
- `src/main.jsx`: `Workspace` component toggles between `CatalogApp` (v2 editor,
  default) and `App` (legacy "family expansion" editor); renders into `#root`.
- `src/CatalogApp.jsx` (~294 lines). Key parts:
  - Constants: `STORAGE = 'illumenate-product-catalog-v2'` (drafts in localStorage),
    `PENDING = 'illumenate-erp-reference-pending'` (catalogs downloaded with
    "Add to ERPNext reference"), `parentTypes`, `shortName`.
  - `restore()`, `asNewRecord(doctype, row)` (clears the naming field), `restorePending()`, `download()`.
  - `export function RecordFields({doctype, row, onChange, catalog, reference, filter, depth})`:
    renders every schema field. Link fields get a `<datalist>` built from catalog
    record names + `catalog.external_links[target]` + `Object.keys(reference.doctypes[target].records)`,
    and show "Existing ERPNext record · <summary>" when the value is in the reference.
  - `function ReferencePanel({doctype, reference, onCopy})`: "N existing in ERPNext"
    list with search and **Copy as new record**; `partial = entry.source !== 'export'`
    hides copying for link-only lists.
  - `export default function CatalogApp({onLegacy})`: state `workspace`, `selected`,
    `search`, `fieldSearch`, `message`, `showPreview`, `confirm`, `undo`, `exported`
    (the loaded reference), `pending`. The reference loads lazily:
    ```js
    useEffect(() => {
      // The ERPNext export is large, so it loads after the editor opens.
      import('./erp-reference.json').then(module => setExported(module.default))
        .catch(() => setMessage('Existing ERPNext records could not be loaded. Declare existing records manually.'));
    }, []);
    ```
    Derived: `known = mergeAdditions(exported, pending, schema)`,
    `reference = excludeCatalog(known, catalog)`, `resolved = withReferenceLinks(catalog, schema, reference)`,
    `yaml`, `issues = catalogIssues(...)`, `missing = unresolvedLinks(...)`,
    `unconfirmed = unconfirmedLinks(...)`.
  - Header actions: **Family expansion editor**, **Open YAML**, **Save draft**,
    **Download catalog** (`disabled={issues.length > 0}`; adds a pending catalog when
    `add_to_reference`). Toolbar: catalog name, **Add to ERPNext reference after import**
    checkbox, counts, **Load example**, **Clear draft**.
  - Right aside `.catalog-review` ("Import readiness"): reference status text
    ("export of <date>"), pending catalogs, **Create missing Item records**,
    unresolved links with **Use existing ERPNext record**, unconfirmed declared links,
    declared external links, validation findings, the CLI command, **Preview YAML**.
  - Confirm modal (`confirm` state with `title` and `run`).
- `src/catalog-model.js` (pure, no React) exports: `recordName`, `blankRecord`,
  `emptyCatalog`, `parseCatalog`, `linkedRecords`, `inReference`, `referenceSummary`,
  `unresolvedLinks`, `withReferenceLinks`, `unconfirmedLinks` (only for
  `source === 'export'`), `catalogKey`, `referenceRecord`, `catalogAddition`,
  `mergeAdditions`, `excludeCatalog`, `referenceOrigin`, `catalogIssues`,
  `makeItemRecords`. Constants `SUMMARY_ONLY = new Set(['ilL-Webflow-Product'])`,
  `SHORT_TYPES`.
- `src/catalog-schema.json` (~170 KB): DocType metadata snapshot,
  `{schema_version: 2, products: {...}, doctypes: {...}}`.
- `src/catalog-examples.json`: one example catalog per family.
- Tests: `tests/catalog.test.js` (node:test, imports from `../src/catalog-model.js`,
  loads schema/examples JSON) and `tests/render.mjs` (Vite SSR: renders `CatalogApp`,
  every example record via `RecordFields`, and the legacy `App`).

### 2.5 The Python catalog code (`tools/fixture_builder`)

- `catalog_schema.py` — **no Frappe import**:
  - `ROOT = Path(__file__).resolve().parents[2]` (repo root),
    `DOCTYPE_ROOT = ROOT / "illumenate_lighting/illumenate_lighting/doctype"`,
    `SNAPSHOT = ROOT / "tools/yaml_builder_ui/src/catalog-schema.json"`.
  - `NON_VALUE` field types to drop; `PRODUCTS` (product type → `label`, `template`, `spec` DocTypes).
  - `standard_doctypes()`: explicit ERPNext subset — Item (+ `attributes` → Item Variant
    Attribute, `supplier_items` → Item Supplier with site custom field
    `custom_supplier_description`), Item Attribute (+ Item Attribute Value),
    Item Group, UOM, Brand, Item Price.
  - `build_schema()`: reads every DocType JSON under `DOCTYPE_ROOT`, selects
    non-table DocTypes named `ilL-Attribute-*`, `ilL-Spec-*`, `ilL-Rel-*`,
    `*-Template`, `*-Submittal-Mapping`, `ilL-Webflow-Product`, `ilL-Webflow-Category`,
    plus every reachable child table; keeps field keys `fieldname, label, fieldtype,
    options, reqd, default, description, read_only`. Result: **65 parent + 37 child DocTypes**.
  - `main()`: writes the snapshot, or `--check` fails if it is stale (byte comparison).
- `catalog.py` — imports `record_issues` from
  `illumenate_lighting.illumenate_lighting.api.authoring_contract` (pure, no Frappe)
  and `PRODUCTS, build_schema` from `.catalog_schema`:
  - Constants: `TABLES`, `NUMBERS`, `CONFIGURATION_TABLES`, `WEBFLOW_TEMPLATES`, `AXES`.
  - `identity(doctype, record, schema)`: record name from autoname
    (`field:x` → `record[x]`; `format:{a}-{b}` → substituted; otherwise `record["name"]`).
  - `with_defaults()`, `_record_errors()` (types, required, Select choices, then
    `record_issues` engineering checks and `_configuration_errors`), `links(doctype, record, schema, path)`
    (yields `(target_doctype, value, path)` for Link and Dynamic Link, recursing into
    child tables; target may be `None` for an unset Dynamic Link), `_variant_errors()`.
  - **`prepare_catalog(config, schema=None, reference=None)`** → `(records, batches, used_external)`.
    `reference` is `{doctype: set(names)}` of records that exist in ERPNext.
    Raises `ValueError("\n".join(errors))` for: unknown top-level keys, bad
    `schema_version`/`product_type`, malformed records, **a record whose name already
    exists in `reference`** ("already exists in ERPNext; remove this record and link to
    the existing one"), unresolved links, circular links. `batches` is an ordered list of
    `(doctype, [records])`; inserting batches in order satisfies every link.
  - `csv_data()`, `generate_catalog(config, output_dir, reference)` (file writing).
- `erp_reference.py` — imports `identity` from `.catalog`, `ROOT, build_schema` from
  `.catalog_schema`. `REFERENCE` path; `SKIPPED_CHILDREN = {"ilL-Child-Webflow-Sync-State", "Item Supplier"}`,
  `SKIPPED_TYPES = {"Currency"}`, `SUMMARY_ONLY = {"ilL-Webflow-Product"}`,
  `SHORT_TYPES = {"Data","Link","Dynamic Link","Select","Int","Float","Check"}`.
  `reference_record(doctype, record, schema)` keeps schema fields only, drops empty
  values, `Currency` fields, skipped children; Webflow Product keeps short fields only.
  `load_reference()`, `unconfirmed_links()`, `catalog_key()`, `add_catalog()`, `build_reference()`, `parse_export()`.
- `__main__.py` — CLI; v2 path calls `prepare_catalog` / `generate_catalog` /
  `load_reference` / `add_catalog`.
- Tests import these names, which must keep working:
  `tools.fixture_builder.catalog`: `CONFIGURATION_TABLES, WEBFLOW_TEMPLATES, csv_data, generate_catalog, identity, links, prepare_catalog, with_defaults`;
  `tools.fixture_builder.catalog_schema`: `PRODUCTS, ROOT, SNAPSHOT, build_schema`;
  `tools.fixture_builder.erp_reference`: `REFERENCE, add_catalog, build_reference, load_reference, parse_export, unconfirmed_links`.
- Test run on 2026-10-05: `python -m unittest discover -s tools/fixture_builder/tests -q` → **132 tests OK**.

### 2.6 Roles and permissions

- Capabilities: `illumenate_lighting/illumenate_lighting/portal/staff.py`.
  `CAPABILITIES["catalog"] = {"ilL Catalog Publisher"}`. `allowed(capability, user=None)`
  is true for `Administrator`, and for enabled **System Users** holding a capability
  role or `System Manager`. `require(capability)` throws
  `frappe.PermissionError("This action requires an authorized staff account")`.
- **Role permissions are managed in code**: `illumenate_lighting/portal_staff_permissions.py`.
  - `authoring_permissions(names)` returns `{doctype: set(ptypes)}`: read/select/write/
    create/report/import/export on every `ilL-Spec-*`, `ilL-Attribute-*`, `ilL-Rel-*`
    DocType plus `ilL-Fixture-Template`, `ilL-Tape-Neon-Template`, `ilL-LED-Sheet-Template`,
    `ilL-Driver-Template`, `ilL-Controller-Template`, the five `*-Submittal-Mapping`
    DocTypes and `ilL-Item-Literature`; and **read/select only** on `Item`, `UOM`,
    `Item Group`, `Brand`, `ilL-Webflow-Product`, `ilL-Webflow-Category`.
  - `apply_service_permissions()` gives `ilL Catalog Publisher` the `authoring_permissions`
    matrix, upgrades `ilL-Webflow-Product` and `ilL-Webflow-Category` to full authoring,
    and `ilL-Webflow-Brand` read/select. It creates missing roles, `add_permission(doctype, role, 0)`,
    then `update_permission_property(doctype, role, 0, ptype, 0|1, validate=False)` for each ptype.
  - It runs from patches (`patches/b2b_authoring_roles.py` → `apply_staff_permissions()`,
    which ends by calling `apply_service_permissions()`). Patches run **once per patch
    name**, so new permissions need a **new patch module**.
- **Current gaps for this feature** (computed from the code): with today's matrix,
  `ilL Catalog Publisher` **cannot create**: `Item`, `Item Attribute`, `Item Group`,
  `UOM`, `Brand`, `Item Price`, and **`ilL-Extrusion-Kit-Template`** (missing from
  `authoring_permissions`' template list). Session 3 fixes this.
- `authoring_permissions` is also used by `ilL Engineering` and by
  `api/product_readiness.py::authoring_preview` (as an allow-list of authorable
  DocTypes). Adding `ilL-Extrusion-Kit-Template` there is intended for both.

### 2.7 Desk workspace

- `illumenate_lighting/illumenate_lighting/workspace/illumenate_lighting/illumenate_lighting.json`
  ("ilLumenate Lighting" workspace). `shortcuts` rows look like
  `{"label": "Fixture Template", "link_to": "ilL-Fixture-Template", "type": "DocType"}`;
  `content` is a JSON string of blocks like
  `{"id": "ill_b2b_ill_publish_job", "type": "shortcut", "data": {"shortcut_name": "Publication Jobs", "col": 3}}`.
- `illumenate_lighting/portal_workspace.py` (`before_migrate` / `after_migrate` hooks)
  **merges** the shipped workspace into the site's edited one: shortcut rows are added
  by identity `(type, link_to, label)`, content blocks by `id`. So a new shortcut row
  plus a content block with a **new unique id** is added without overwriting site edits.

### 2.8 Deployment (Frappe Cloud)

- Production: `illumenatelighting.v.frappe.cloud`, deployed from `main`.
  Staging: `stagingillumenate.v.frappe.cloud` (see §1 note), deployed from the
  `staging` branch on a separate bench group. Release flow: feature PR →
  `staging` → staging deploy and checks → PR `staging` → `main` → production deploy.
- Frappe Cloud runs a **Pull** update (new code, no `bench migrate`) unless the diff
  touches `*/patches.txt`, `*/hooks.py`, `*/fixtures/`, `*/*/custom/`, or a
  DocType / Workspace / Report / Print Format / Page JSON; any of those makes it a
  **Migrate** update (source: `docs/DEPLOYMENT_RECOVERY_PLAN_2026_09_29.md` §6).
  Built assets in `public/` ship with the code.
- The bench clones the **whole git repository** into `apps/illumenate_lighting`, so
  `tools/` exists on disk next to the package (assumption used only by Session 1's
  temporary snapshot endpoint; Session 2 removes the dependency).

### 2.9 Tests and CI

- `.github/workflows/b2b-contracts.yml` (Python 3.11, Node 22), steps:
  `python -B -m unittest discover -s tests/portal_unit`;
  `python -B -m unittest discover -s tools/fixture_builder/tests`;
  `python -B tools/check_portal_templates.py`; Node tests under `tests/portal_ui` and
  `tests/portal_unit`; Product Finder bundle freshness; `tools/check_pdf_fidelity.py`;
  spec-sheet tests; `tools/check_b2b_changes.py` (no **new** ruff findings in changed
  files compared with the base; JSON files must parse).
- `.github/workflows/ci.yml` ("Server (version-16)"): installs bench, ERPNext and the
  app on MariaDB, migrates twice, then runs **only listed modules**:
  `bench --site test_site run-tests --app illumenate_lighting --module <dotted.module>`.
  A new bench test module must be **added to that list**. A second job installs the
  base revision and migrates to the PR head, so new patches really execute there.
- `.github/workflows/linter.yml`: pre-commit (Python 3.10) and Semgrep with
  `frappe/semgrep-rules` (flags e.g. manual `frappe.db.commit()`; justify any you add
  with a `# nosemgrep` comment and a reason).
- Bench-free unit tests: `tests/portal_unit/test_services.py::load_service(relative, extras)`
  loads a module by dotted path with a fake `frappe` module installed: `frappe.whitelist`
  (records `whitelist_options`), `frappe.throw` (raises `ValueError` or the given
  class), `frappe.PermissionError = PermissionError`, `frappe.ValidationError = ValueError`,
  `MagicMock`s for `frappe.db`, `get_all`, `get_doc`, `cache`, `get_roles`
  (default `["Dealer"]`), `frappe.session = Record(user="buyer@example.com")`,
  `frappe.local`, `frappe.flags`, a small `frappe.utils`. Usage pattern
  (`tests/portal_unit/test_catalog_repair.py`):
  ```python
  from test_services import ROOT, Record, load_service
  with load_service(ROOT + ".portal.catalog_repair") as (service, frappe):
      frappe.get_all.return_value = [...]
      ...
  ```
- Bench test classes: most files use `from frappe.tests.utils import FrappeTestCase`;
  v16's preferred `from frappe.tests import IntegrationTestCase` is also used. Either works.

### 2.10 Document hooks that fire on insert

`doc_events` in `hooks.py` attach `after_insert`/`on_update` handlers from
`api/webflow_sync_events.py` to attribute DocTypes and `ilL-Webflow-Product`. They only
write DB flags (`frappe.db.set_value(..., "Pending")`), call
`publication.invalidate_product` for Webflow Products, and use `frappe.log_error` on
failure. They make no HTTP calls and enqueue nothing, so they roll back cleanly.
ERPNext's own `Item` controller still has to be proven on staging (Session 5).

---

## 3. Verified Frappe v16 behaviour this plan relies on

Checked in `frappe/frappe@version-16` on 2026-10-05.

| Behaviour | Where | Consequence for this plan |
|---|---|---|
| A page template is wrapped in the base template **unless** its source contains `{% extends` or `</body>` | `website/page_renderers/template_page.py::set_properties_from_source` | A standalone HTML document with `</body>` renders as-is, without website chrome. |
| Any exception from a request handler → `db.rollback(chain=True)`; a successful POST/PUT/DELETE (or `frappe.local.flags.commit`) → `db.commit(chain=True)`; GET → rollback | `app.py` (`application`, `sync_database`) | Endpoints must **not raise** after writing the audit log, or the log is lost. Return a result dict instead. GET endpoints cannot write. |
| `frappe.db.savepoint(name)`, `frappe.db.rollback(save_point=name)`, `frappe.db.release_savepoint(name)` | `database/database.py` | Per-record savepoints let a dry run continue after a failed record. Rollback-to-savepoint does not run rollback watchers (file writes are not undone; there are none here). |
| `frappe.db.rollback()` (no savepoint) rolls back and begins a new transaction | same | Safe to write and commit the log afterwards. |
| Implicit commit: DDL (`create`, `alter`, `drop`, `truncate`, `begin`, `start`) inside a transaction with writes raises an error | `database.py::check_implicit_commit` | Nothing in a catalog insert should run DDL; if it does, the run fails loudly (good). |
| Request body limit: `conf.max_file_size` or **25 MB** for non-upload requests | `app.py` | 500 records fit easily. |
| `Document.insert(ignore_permissions=None, ignore_links=None, ignore_if_duplicate=False, ignore_mandatory=None, set_name=None, set_child_names=True)` | `model/document.py` | Use plain `insert()` for catalog records; `ignore_permissions=True` only for the audit log. |
| `frappe.local.message_log` is a list of message dicts (`{"message", "title", "indicator", ...}`) appended by `msgprint` / `throw` | `__init__.py` | Capture warnings per record by clearing it before and reading it after `insert()`. |
| `frappe.sessions.get_csrf_token()` | `sessions.py` | Pass to the page; send as `X-Frappe-CSRF-Token` on POST. |
| `frappe.desk.search.search_link(doctype, txt, query=None, filters=None, page_length=10, ...)` (whitelisted) | `desk/search.py` | Optional server-side type-ahead for large DocTypes. |
| `frappe.cache().set_value(key, val, user=None, expires_in_sec=None)` / `get_value(key, ...)` | `utils/redis_wrapper.py` | Cache the live reference for a few minutes. |
| JSON request bodies (`Content-Type: application/json`) become `frappe.form_dict` keyword arguments | `app.py::make_form_dict`, `handler.py::execute_cmd` | `fetch(..., {body: JSON.stringify({catalog, expected_hash})})` maps to `def import_catalog(catalog, expected_hash)`; `catalog` may arrive as a dict. Use `frappe.parse_json` defensively. |

---

## 4. Glossary

- **Catalog**: the v2 YAML/JSON document above.
- **Reference**: the set of records that already exist in ERPNext, shaped like
  `erp-reference.json` (`{schema_version, exported_on, doctypes: {DocType: {source, exported_on, records: {name: {fields}}}}}`).
  `source` is `"export"` (complete list from an export), `"links"`/`"catalog"` (partial),
  and from Session 2 `"live"` (complete list from the site).
- **Batch**: one `(doctype, [records])` entry from `prepare_catalog`; batches are in
  dependency order.
- **Check**: dry-run import that always rolls back. **Import**: real insert, all-or-nothing.
- **ERP mode / Vercel mode**: the same React app mounted by the ERPNext page vs. the
  static Vercel build. ERP-only behaviour is switched by a `mode` prop.

---

## 5. Ground rules, local setup and commands

### 5.1 Rules for every session

- Branch from the latest `main`; one PR per session into `main` (the owner then
  promotes via `staging`). Keep diffs to the session's scope.
- **The Vercel build and the CLI must keep working after every session.**
- Never put site data or secrets under `illumenate_lighting/public/`.
- Built bundles are committed (like the Product Finder) and CI checks freshness.
- Update `tools/yaml_builder_ui/README.md` and `tools/fixture_builder/CATALOG.md` in
  the same PR when behaviour changes. Match the existing terse style.
- Python must stay 3.10-compatible. No new runtime dependencies (the app's
  `pyproject.toml` dependencies are only `pypdf` and `Pillow`; `PyYAML` is **not** a
  server dependency, so server code accepts JSON only).
- Don't edit generated files by hand: regenerate `catalog-schema.json` with
  `python -m tools.fixture_builder.catalog_schema` and bundles with the npm build.

### 5.2 Commands to run before every push

From the repo root:

```bash
python -m pip install ruff PyYAML              # once
ruff check .
ruff format --check <changed .py files>
python -m tools.fixture_builder.catalog_schema --check
python -B -m unittest discover -s tools/fixture_builder/tests
python -B -m unittest discover -s tests/portal_unit
python -B tools/check_portal_templates.py
B2B_BASE_REF=origin/main python -B tools/check_b2b_changes.py
cd tools/yaml_builder_ui && npm ci && npm test && npm run test:render && npm run build && cd -
# from Session 1 on:
npm run build:erp --prefix tools/yaml_builder_ui && git diff --exit-code illumenate_lighting/public/catalog_builder
```

`tests/portal_unit` may need extra packages (CI installs `ruff PyYAML Jinja2 Pillow pypdf reportlab pypdfium2`).

### 5.3 Local Frappe bench (for page, endpoint and bench tests)

Mirrors `ci.yml`. Needs MariaDB 10.6+ and Redis.

```bash
pip install frappe-bench
bench init --frappe-branch version-16 --skip-redis-config-generation ~/frappe-bench
cd ~/frappe-bench
bench get-app erpnext --branch version-16
bench get-app illumenate_lighting /path/to/erpillumenatelighting   # local checkout
bench new-site --db-root-password <root-pw> --admin-password admin catalog.localhost
bench --site catalog.localhost install-app erpnext
bench --site catalog.localhost install-app illumenate_lighting
bench --site catalog.localhost set-config developer_mode 1
bench --site catalog.localhost set-config allow_tests true
bench build --app illumenate_lighting
bench start                                   # http://catalog.localhost:8000
bench --site catalog.localhost run-tests --app illumenate_lighting --module <dotted.module>
```

Complete the ERPNext setup wizard (company, currency) on the new site, or Item
inserts will fail for missing defaults. If no bench is available, say so in the PR
and rely on unit tests plus the staging check in Session 5.

### 5.4 PR description template (use for every session)

```
## Session N — <title>
Plan: docs/CATALOG_BUILDER_IN_ERPNEXT_PLAN.md §<n>

### What changed
### Deploy type: Pull | Migrate (why)
### How I verified (commands + results; bench/staging checks done or not done)
### Differences from the plan
### Follow-ups
```

---

## 6. Session 1 — Host the builder inside ERPNext

**Goal:** the existing builder runs at `/catalog-builder` for logged-in catalog
staff. The reference snapshot comes from an authenticated endpoint instead of the
bundle. The editor's behaviour is otherwise unchanged; Vercel keeps working.

### 6.1 Starting-state check

```bash
git checkout main && git pull
test -f tools/yaml_builder_ui/src/erp-reference.json && echo snapshot ok
grep -n '"/portal/product-finder"' illumenate_lighting/hooks.py
ls illumenate_lighting/public/product_finder
```

### 6.2 Read first

`tools/yaml_builder_ui/src/main.jsx`, `src/CatalogApp.jsx` (lines 1–45 and 143–175),
`vite.config.js`, `package.json`, `vercel.json`, `tests/render.mjs`;
`tools/configurator_ui/vite.config.js`, `vite.portal.config.js`;
`illumenate_lighting/templates/pages/product_finder.py` and `.html`;
`illumenate_lighting/hooks.py` (`website_route_rules`);
`illumenate_lighting/illumenate_lighting/portal/staff.py`;
`illumenate_lighting/illumenate_lighting/workspace/illumenate_lighting/illumenate_lighting.json`;
`illumenate_lighting/portal_workspace.py` (`merge_workspace`);
`.github/workflows/b2b-contracts.yml`; `tools/check_portal_templates.py`;
`tests/portal_unit/test_services.py` (lines 1–75).

### 6.3 Files

| New | Changed |
|---|---|
| `tools/yaml_builder_ui/src/erp-main.jsx`, `src/Workspace.jsx` | `tools/yaml_builder_ui/src/main.jsx` |
| `tools/yaml_builder_ui/vite.erp.config.js` | `tools/yaml_builder_ui/src/CatalogApp.jsx` |
| `illumenate_lighting/public/catalog_builder/catalog-builder.js` (built) | `tools/yaml_builder_ui/package.json` |
| `illumenate_lighting/public/catalog_builder/catalog-builder.css` (built) | `tools/yaml_builder_ui/tests/render.mjs` |
| `illumenate_lighting/illumenate_lighting/api/catalog_builder.py` | `illumenate_lighting/hooks.py` |
| `illumenate_lighting/templates/pages/catalog_builder.py` | workspace JSON (shortcut) |
| `illumenate_lighting/templates/pages/catalog_builder.html` | `.github/workflows/b2b-contracts.yml` |
| `tests/portal_unit/test_catalog_builder.py` | `tools/yaml_builder_ui/README.md` |

### 6.4 Steps

**Step 1 — Make the reference loader and mode injectable (no behaviour change).**

`CatalogApp.jsx` must contain **no** import of `erp-reference.json` (see Step 2 for
why). Make the loader a required prop and add a `mode` prop:

```jsx
export default function CatalogApp({ onLegacy, loadReference, mode = 'vercel' }) {
  ...
  useEffect(() => {
    // The ERPNext records are large, so they load after the editor opens.
    loadReference()
      .then(data => {
        setExported(data);
        if (data?.unavailable) setMessage('Existing ERPNext records are unavailable. Declare existing records manually.');
      })
      .catch(() => setMessage('Existing ERPNext records could not be loaded. Declare existing records manually.'));
  }, [loadReference]);
```

Move `Workspace` out of `main.jsx` into `src/Workspace.jsx` (default export) and
have it accept and pass `loadReference`, `mode` (and later `api`) to `CatalogApp`.
`main.jsx` (Vercel entry) becomes:

```jsx
const loadSnapshot = () => import('./erp-reference.json').then(module => module.default);
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><Workspace loadReference={loadSnapshot} /></React.StrictMode>);
```

`loadSnapshot` is defined at module level so its identity is stable (the effect
depends on it). `mode` changes nothing visible in Session 1; it is plumbing for
Sessions 2 and 4.

**Step 2 — ERP entry point `src/erp-main.jsx`.**

```jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import Workspace from './Workspace.jsx';
import './index.css';

export function mount(elementId, { referenceUrl, csrfToken }) {
  const loadReference = () => fetch(referenceUrl, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    .then(response => {
      if (response.status === 401 || response.status === 403) throw new Error('Your ERPNext session has expired. Reload the page to log in again.');
      if (!response.ok) throw new Error(`ERPNext returned ${response.status}`);
      return response.json();
    })
    .then(body => body.message);
  ReactDOM.createRoot(document.getElementById(elementId)).render(
    <React.StrictMode><Workspace loadReference={loadReference} mode="erp" csrfToken={csrfToken} /></React.StrictMode>);
}
```

It must not import `erp-reference.json` directly or indirectly. An IIFE build cannot
split code, so any `import('./erp-reference.json')` reachable from `erp-main.jsx`
would **inline** the 4.3 MB file into the bundle even if ERP mode never calls it. That
is why the snapshot loader lives only in `main.jsx` (Step 1). Define `loadReference`
at module level or with `useMemo`/`useCallback` so its identity is stable.
`tests/render.mjs` must pass a `loadReference` stub (e.g. `() => new Promise(() => {})`).

**Step 3 — Build config `tools/yaml_builder_ui/vite.erp.config.js`.**

```js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  base: '/assets/illumenate_lighting/catalog_builder/',
  build: {
    outDir: resolve(import.meta.dirname, '../../illumenate_lighting/public/catalog_builder'),
    emptyOutDir: true,
    lib: { entry: resolve(import.meta.dirname, 'src/erp-main.jsx'), name: 'IllCatalogBuilder', formats: ['iife'], fileName: () => 'catalog-builder.js' },
    cssCodeSplit: false,
    rollupOptions: { output: { assetFileNames: 'catalog-builder.[ext]' } },
  },
});
```

`package.json`: add `"build:erp": "npm run schema:check && vite build --config vite.erp.config.js"`.
Leave `build`, `vercel.json` and `vite.config.js` alone.

After building, verify:

```bash
ls -la illumenate_lighting/public/catalog_builder/          # exactly catalog-builder.js and catalog-builder.css
grep -c '"exported_on"' illumenate_lighting/public/catalog_builder/catalog-builder.js   # must print 0
grep -c 'catalog-builder' illumenate_lighting/public/catalog_builder/catalog-builder.js # sanity
du -h illumenate_lighting/public/catalog_builder/*         # expect JS well under 1 MB (schema JSON ~170 KB is inlined)
```

Build twice and confirm byte-identical output (`git diff --exit-code` after the second
build); CI relies on reproducible builds.

**Step 4 — Reference endpoint `illumenate_lighting/illumenate_lighting/api/catalog_builder.py`.**

```python
"""Catalog Builder service: the YAML builder's data, served to catalog staff."""

import json
from pathlib import Path

import frappe

from illumenate_lighting.illumenate_lighting.portal.staff import require

# Temporary (Session 1): the committed snapshot. Session 2 replaces it with live records.
# api/ -> illumenate_lighting/illumenate_lighting -> illumenate_lighting -> repo root
SNAPSHOT = Path(__file__).resolve().parents[3] / "tools/yaml_builder_ui/src/erp-reference.json"


@frappe.whitelist(methods=["GET"])
def reference():
	require("catalog")
	if not SNAPSHOT.is_file():
		return {"schema_version": 1, "exported_on": None, "doctypes": {}, "unavailable": True}
	return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
```

`parents[3]` needs no Frappe call at import time, so unit tests can load the module;
on the bench it resolves to `apps/illumenate_lighting` (the cloned repo root). In the UI, when `unavailable` is true, show "Existing ERPNext records are unavailable;
declare existing records manually." (reuse `setMessage`).

**Step 5 — Page.**

`illumenate_lighting/templates/pages/catalog_builder.py`:

```python
"""Catalog Builder: the YAML builder for catalog staff, on this site."""

from pathlib import Path

import frappe
from frappe import _

no_cache = 1
ASSETS = "/assets/illumenate_lighting/catalog_builder/catalog-builder"
BUNDLE = Path(__file__).resolve().parents[2] / "public/catalog_builder/catalog-builder.js"


def get_context(context):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/catalog-builder"
		raise frappe.Redirect
	if not allowed("catalog"):
		frappe.throw(_("Catalog staff access is required"), frappe.PermissionError)
	version = int(BUNDLE.stat().st_mtime) if BUNDLE.exists() else 0
	context.update(
		{
			"title": "Catalog Builder",
			"no_cache": 1,
			"assets": ASSETS,
			"asset_version": version,
			"mount_options": {
				"csrfToken": frappe.sessions.get_csrf_token(),
				"referenceUrl": "/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.reference",
				"user": frappe.session.user,
			},
		}
	)
	return context
```

Check `parents[2]`: `pages` → `templates` → `illumenate_lighting` (package) → so
`parents[2] / "public"` is `illumenate_lighting/public`. Confirm with a test.
`st_mtime` changes on every deploy checkout, which is fine for cache-busting; a content
hash is also acceptable (`hashlib.sha256(BUNDLE.read_bytes()).hexdigest()[:12]`, cached at import).

`illumenate_lighting/templates/pages/catalog_builder.html` — a **complete document**
(the `</body>` tag stops Frappe wrapping it in the website base template, see §3):

```html
<!doctype html>
<html lang="en">
<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<meta name="robots" content="noindex">
	<title>Catalog Builder · ilLumenate</title>
	<link rel="stylesheet" href="{{ assets }}.css?v={{ asset_version }}">
</head>
<body>
	<div id="catalog-builder-root"></div>
	<script src="{{ assets }}.js?v={{ asset_version }}"></script>
	<script>IllCatalogBuilder.mount("catalog-builder-root", {{ mount_options | tojson }});</script>
</body>
</html>
```

Jinja's `tojson` escapes `<`, `>`, `&`, `'`, so embedding in `<script>` is safe.

**Step 6 — Route.** In `hooks.py` `website_route_rules`, add near the other non-portal rules:
`{"from_route": "/catalog-builder", "to_route": "catalog_builder"},`.
Touching `hooks.py` makes the deploy a **Migrate** update.

**Step 7 — Desk shortcut.** In the workspace JSON add to `shortcuts`:
`{"label": "Catalog Builder", "type": "URL", "url": "/catalog-builder"}` and to the
`content` JSON string a block
`{"id": "ill_catalog_builder", "type": "shortcut", "data": {"shortcut_name": "Catalog Builder", "col": 3}}`.
Keep the file's key order and formatting; bump `modified`. `merge_workspace` adds it to
the site's workspace on migrate without overwriting site edits (§2.7). The shortcut
is visible to everyone who sees the workspace; the page itself enforces the role.

**Step 8 — CI.** In `b2b-contracts.yml`, after "Product Finder bundles are fresh", add:

```yaml
      - name: Catalog Builder bundle is fresh
        run: |
          npm ci --prefix tools/yaml_builder_ui
          npm test --prefix tools/yaml_builder_ui
          npm run test:render --prefix tools/yaml_builder_ui
          npm run build:erp --prefix tools/yaml_builder_ui
          git diff --exit-code illumenate_lighting/public/catalog_builder
```

(`build:erp` runs `schema:check`, which needs Python on PATH — present in that job.)
`check_portal_templates.py` parses the new template automatically; add a render case
only if the script renders comparable pages (it renders specific ones with stub
context — follow its pattern if you add one, with `assets`, `asset_version`,
`mount_options` stubs).

**Step 9 — Tests.**

`tests/portal_unit/test_catalog_builder.py`:

```python
import unittest
from unittest.mock import patch

from test_services import ROOT, load_service


class CatalogBuilderReference(unittest.TestCase):
	def test_non_catalog_users_are_refused(self):
		with load_service(ROOT + ".api.catalog_builder") as (service, frappe):
			# staff.allowed reads User enabled/user_type and roles; Dealer has no catalog capability
			frappe.db.get_value.side_effect = lambda doctype, name, field: {"enabled": 1, "user_type": "System User"}[field]
			with self.assertRaises(PermissionError):
				service.reference()

	def test_catalog_user_gets_snapshot(self): ...        # get_roles -> ["ilL Catalog Publisher"]
	def test_missing_snapshot_is_reported_not_raised(self): ...   # patch service.SNAPSHOT to a temp path
```

`staff.py` is imported by the service; `load_service` installs the fake `frappe`
before execution, and `staff.py` will import that fake. If `staff` was imported
earlier in the test process with a different fake, pass it through `extras` or
reload it — mirror how `test_catalog_repair.py` / `test_publication.py` handle `staff`.
Also test the page module (`ROOT` is `illumenate_lighting.illumenate_lighting`;
the page lives in `illumenate_lighting.templates.pages.catalog_builder`, so call
`load_service("illumenate_lighting.templates.pages.catalog_builder")`): Guest →
`frappe.Redirect` raised and `redirect_location` set; Dealer → PermissionError;
catalog user → context has `mount_options.csrfToken`. Add `frappe.Redirect`,
`frappe.sessions.get_csrf_token` stubs to the fake as needed (per test, not by
editing `test_services.py`, unless several tests need them).

`tests/render.mjs`: pass `loadReference: () => new Promise(() => {})` and assert the
shell still renders; add one render with `mode: 'erp'`.

**Step 10 — Docs.** README: new section "Use the builder in ERPNext" — URL, required
role, drafts are per site (move them with **Save draft** / **Open YAML**), records
come from the snapshot until the next release, Vercel unchanged; how to rebuild the
ERP bundle (`npm run build:erp`) and that CI checks it.

### 6.5 Verification

- Unit tests and all §5.2 commands pass.
- On a local bench (if available): log out → open `/catalog-builder` → login page →
  after login back on the builder. As a System User without the role → 403 page.
  As Administrator → editor loads; link suggestions show "Existing ERPNext record";
  **Download catalog** works. DevTools: `catalog-builder.js` contains no reference
  data; the reference request is `GET /api/method/...catalog_builder.reference` → 200.
- `npm run build` still produces `dist/` with a separate lazy chunk for the reference
  (Vercel mode unchanged).

### 6.6 Deploy notes

**Migrate** update (hooks.py, workspace JSON). After deploy: open `/catalog-builder`;
if the reference is `unavailable`, `tools/` is not on the bench — note it for Session 2,
which removes the dependency.

### 6.7 Acceptance

Page works for catalog users only; bundle has no site data; Vercel unchanged; all CI green.

### 6.8 Out of scope

Live data, Check/Import, any change to `catalog-model.js` logic, any visual change.

---

## 7. Session 2 — Shared catalog code in the app + live ERPNext data

**Goal:** (a) move the pure catalog code into the installed app package so the server
can use it (Sessions 2 and 3 both need it); (b) in ERP mode the builder's existing
records come **live** from the site at page load and on **Refresh**; (c) **Copy as new
record** fetches the full record. Vercel and the CLI keep the snapshot workflow.

### 7.1 Starting-state check

Session 1 merged: `illumenate_lighting/illumenate_lighting/api/catalog_builder.py`
and `public/catalog_builder/` exist; `/catalog-builder` route present in `hooks.py`.

### 7.2 Read first

`tools/fixture_builder/catalog.py`, `catalog_schema.py`, `erp_reference.py` (all),
`__main__.py` (v2 path), `tools/fixture_builder/tests/test_catalog.py` and
`test_erp_reference.py` (imports), `src/catalog-model.js` (reference helpers),
`src/CatalogApp.jsx` (`ReferencePanel`, review aside, toolbar), Session 1's files.

### 7.3 Part A — Move the shared code (behaviour-neutral)

Create the package `illumenate_lighting/illumenate_lighting/catalog_authoring/`:

| New module | Contents (moved verbatim unless noted) |
|---|---|
| `__init__.py` | Docstring only: "Pure product-catalog logic shared by the CLI and the site. No Frappe imports." |
| `schema.py` | From `catalog_schema.py`: `NON_VALUE`, `PRODUCTS`, `_field`, `standard_doctypes`, `build_schema`. `DOCTYPE_ROOT = Path(__file__).resolve().parents[1] / "doctype"`. **Not** `ROOT`, `SNAPSHOT`, `main`. Add `@functools.lru_cache(maxsize=1)` wrapper `cached_schema()` that returns `build_schema()` (callers must not mutate it; document that). |
| `catalog.py` | From `catalog.py`: constants, `identity`, `with_defaults`, `_record_errors`, `_configuration_errors`, `links`, `_axis_value`, `_variant_errors`, `prepare_catalog`, `csv_data`. Imports `record_issues` from `..api.authoring_contract` and `PRODUCTS, build_schema` from `.schema`. **Not** `generate_catalog` (file writing stays in tools). |
| `reference.py` | From `erp_reference.py`: `TABLES`, `SKIPPED_CHILDREN`, `SKIPPED_TYPES`, `SUMMARY_ONLY`, `SHORT_TYPES`, `reference_record`, `_linked`, `catalog_key`. |

Then turn the tools modules into thin re-exports so every existing import works:

```python
# tools/fixture_builder/catalog_schema.py
"""..." (keep docstring)"""
from __future__ import annotations
import json
from pathlib import Path
from illumenate_lighting.illumenate_lighting.catalog_authoring.schema import (  # noqa: F401
	NON_VALUE, PRODUCTS, build_schema, standard_doctypes,
)
ROOT = Path(__file__).resolve().parents[2]
DOCTYPE_ROOT = ROOT / "illumenate_lighting/illumenate_lighting/doctype"
SNAPSHOT = ROOT / "tools/yaml_builder_ui/src/catalog-schema.json"
def main(): ...   # unchanged
```

Same for `catalog.py` (re-export + keep `generate_catalog`) and `erp_reference.py`
(import the moved names; keep everything else). `__all__` or `# noqa: F401` keeps ruff
quiet about re-exports.

Rules: **no `import frappe`** anywhere in `catalog_authoring/`; keep tab indentation;
keep docstrings. Verify behaviour-neutrality:

```bash
python -m tools.fixture_builder.catalog_schema --check      # byte-identical snapshot
python -B -m unittest discover -s tools/fixture_builder/tests   # 132 OK
for f in tools/fixture_builder/templates/catalog_*.yaml; do
  python -m tools.fixture_builder --config "$f" --output /tmp/before/$(basename $f .yaml) >/dev/null   # run on main first
done   # then on the branch into /tmp/after and: diff -r /tmp/before /tmp/after  → no differences
```

`illumenate_lighting.illumenate_lighting` must be importable without Frappe for the CLI
(it already is: `tools/fixture_builder/catalog.py` imports
`illumenate_lighting.illumenate_lighting.api.authoring_contract` today). Check that
`illumenate_lighting/__init__.py` and `illumenate_lighting/illumenate_lighting/__init__.py`
do not import Frappe; if they do, stop and report.

### 7.4 Part B — Live reference on the server

In `api/catalog_builder.py` replace the Session 1 snapshot reader:

```python
from datetime import datetime

from illumenate_lighting.illumenate_lighting.catalog_authoring.reference import (
	SHORT_TYPES, SKIPPED_TYPES, SUMMARY_ONLY, reference_record,
)
from illumenate_lighting.illumenate_lighting.catalog_authoring.schema import cached_schema

CACHE_SECONDS = 300
# Prices are never listed; Item Price records are only identified by hash names.
NOT_LISTED = {"Item Price"}
# Long or file-valued fields are left out of the picker list; Copy as new fetches them.
LIST_SKIPPED_TYPES = SKIPPED_TYPES | {
	"Text Editor", "Long Text", "Text", "Small Text", "HTML Editor", "Markdown Editor",
	"Code", "JSON", "Attach", "Attach Image",
}


@frappe.whitelist(methods=["GET"])
def reference(refresh=0):
	require("catalog")
	key = "ill_catalog_builder_reference"
	if not frappe.utils.cint(refresh):
		cached = frappe.cache().get_value(key, user=frappe.session.user)
		if cached:
			return cached
	data = live_reference()
	frappe.cache().set_value(key, data, user=frappe.session.user, expires_in_sec=CACHE_SECONDS)
	return data


def live_reference():
	schema = cached_schema()
	now = frappe.utils.now_datetime().isoformat(timespec="seconds")
	doctypes, skipped = {}, []
	for doctype, meta in schema["doctypes"].items():
		if meta.get("istable") or doctype in NOT_LISTED:
			continue
		if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
			skipped.append(doctype)
			continue
		live = frappe.get_meta(doctype)
		fields = [
			f["fieldname"] for f in meta["fields"]
			if f["fieldtype"] not in LIST_SKIPPED_TYPES | {"Table", "Table MultiSelect"}
			and (doctype not in SUMMARY_ONLY or f["fieldtype"] in SHORT_TYPES)
			and live.has_field(f["fieldname"])
		]
		rows = frappe.get_list(doctype, fields=["name", *fields], limit_page_length=0, order_by="name asc")
		doctypes[doctype] = {
			"source": "live",
			"exported_on": now,
			"records": {row.pop("name"): {k: v for k, v in row.items() if v not in (None, "", 0)} for row in rows},
		}
	return {"schema_version": 1, "exported_on": now, "source": "live", "doctypes": doctypes, "skipped": skipped}
```

Notes and decisions:

- Standard fields like `item_code` are DB columns, so `has_field` covers the explicit
  standard subset too. For `Item`, `name == item_code`; that is fine.
- `get_list` applies **user permissions** (row-level); `get_all` bypasses them. `has_permission(doctype, "read")`
  is the DocType-level check. Catalog Publisher has read on everything listed after
  Session 3's patch; until then, `skipped` may list some DocTypes — the UI must show it.
- Values `0` are dropped to keep the payload small; `referenceSummary` already ignores
  0 values. If a test shows a UI regression, keep 0 for `Check` fields.
- Performance target: < 3 s uncached on production data (~65 queries; Item has ~2,300
  rows), JSON < 2 MB. Measure on staging in Session 5; if slow, cache per role-set
  instead of per user or narrow Item fields.
- Datetime: use `frappe.utils.now_datetime()` (site timezone).

Full record for **Copy as new record**:

```python
@frappe.whitelist(methods=["GET"])
def record(doctype, name):
	require("catalog")
	schema = cached_schema()
	meta = schema["doctypes"].get(doctype)
	if not meta or meta.get("istable") or doctype in NOT_LISTED:
		frappe.throw(_("Choose a catalog DocType"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return reference_record(doctype, doc.as_dict(), schema)
```

`reference_record` keeps only schema fields, so audit fields, `name`, `idx`, `parent*`
and Currency fields are dropped, and child rows lose their metadata.

### 7.5 Part C — UI (ERP mode only)

1. `catalog-model.js`: add and export
   `export const completeSources = new Set(['export', 'live']);` and
   `export function isComplete(entry) { return completeSources.has(entry?.source); }`.
   Use it in `unconfirmedLinks` (replace `=== 'export'`).
2. `ReferencePanel`: `partial = !isComplete(entry)`; header text: for `live`,
   "Live from ERPNext · loaded HH:MM" (format `entry.exported_on`); otherwise unchanged.
   `onCopy` becomes async: in ERP mode call
   `GET /api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.record?doctype=<dt>&name=<name>`
   and pass the returned record to `asNewRecord`; show `setMessage` on failure.
   Pass a `fetchRecord` prop from `CatalogApp` (undefined in Vercel mode → copy the
   list record as today).
3. Review aside: replace "export of <date>" with "live from ERPNext, loaded HH:MM" when
   `reference.source === 'live'`. If `reference.skipped?.length`, show
   "No read access to: …" in a `<details>`.
4. Add a **Refresh ERPNext records** button (ERP mode only) in the review aside. It
   calls `loadReference({ refresh: true })` (extend the ERP loader to append
   `?refresh=1`) and replaces `exported`. Disable while loading.
5. Hide in ERP mode: the **Add to ERPNext reference after import** checkbox, the
   pending-catalog `<details>`, and the pending side effect of **Download catalog**.
   Pass `pending = []` to `mergeAdditions` in ERP mode. Do not delete the
   `add_to_reference` key from loaded drafts; just ignore it (the server rejects
   nothing about it; `prepare_catalog` accepts it).
6. Keep the "Generate the import package" CLI text in ERP mode for now (Session 4
   replaces it).
7. Large lists: Item has ~2,300 names in a `<datalist>`. Measure typing latency in
   Chrome with production-size data. Only if it lags, switch DocTypes with more than
   1,000 records to server search via `frappe.desk.search.search_link`
   (`GET /api/method/frappe.desk.search.search_link?doctype=Item&txt=<q>&page_length=20`,
   200 ms debounce). Record the measurement in the PR either way.

Rebuild: `npm run build:erp` and commit the bundle.

### 7.6 Tests

- `tools/fixture_builder/tests`: unchanged, green; plus one new test asserting
  `tools.fixture_builder.catalog.prepare_catalog is illumenate_lighting.illumenate_lighting.catalog_authoring.catalog.prepare_catalog`.
- `tests/portal_unit/test_catalog_builder.py`: `live_reference()` with mocked
  `frappe.db.exists`, `has_permission`, `get_meta().has_field`, `get_list`:
  output shape (`source: "live"`, records keyed by name, no `name` inside records),
  Currency/long-text fields not requested (`get_list.call_args.kwargs["fields"]`),
  unreadable DocType in `skipped`, `Item Price` never queried, cache hit skips
  `get_list`, `refresh=1` bypasses cache. `record()`: rejects non-schema DocTypes and
  child tables; strips audit fields.
- `tests/catalog.test.js`: `unconfirmedLinks` flags typos for `source: 'live'`;
  `isComplete`.
- `render.mjs`: ERP mode render shows **Refresh ERPNext records** and no
  add-to-reference checkbox; Vercel mode still shows the checkbox.

### 7.7 Verification

§5.2 commands; the before/after CLI diff in 7.3 is empty. On a bench: create an
attribute value in Desk → **Refresh** → it appears as existing; **Copy as new** on an
`ilL-Rel-Profile Lens` brings its `compatible_lenses` rows.

### 7.8 Deploy notes

**Pull** update (Python, JS and built assets only).

### 7.9 Out of scope

Check/Import, permissions changes, removing the snapshot or `erp_reference.py`.

---

## 8. Session 3 — Server Check/Import engine, audit log, permissions

**Goal:** endpoints that take a catalog, validate it against the live site, and either
dry-run it (Check) or insert it (Import) in one transaction, returning per-record
results; an audit DocType; and the permissions the Catalog Publisher role needs.

### 8.1 Starting-state check

Session 2 merged: `catalog_authoring/` package exists and `api/catalog_builder.py`
has `reference()`/`record()`.

### 8.2 Read first

`catalog_authoring/catalog.py` (`prepare_catalog`, `identity`, `links`),
`api/catalog_builder.py`, `portal/staff.py`, `illumenate_lighting/portal_staff_permissions.py`,
`illumenate_lighting/patches/b2b_authoring_roles.py`, `illumenate_lighting/patches.txt`,
`doctype/ill_export_job/` (JSON + controller + test layout),
`api/publication.py` (endpoint style), `api/webflow_sync_events.py` (insert hooks),
`.github/workflows/ci.yml` (module list), `tests/portal_unit/test_services.py`.

### 8.3 Files

| New | Changed |
|---|---|
| `doctype/ill_catalog_import/__init__.py`, `ill_catalog_import.json`, `ill_catalog_import.py`, `test_ill_catalog_import.py` | `api/catalog_builder.py` |
| `illumenate_lighting/patches/catalog_builder_permissions.py` | `illumenate_lighting/portal_staff_permissions.py` |
| `illumenate_lighting/illumenate_lighting/api/test_catalog_import.py` (bench test) | `illumenate_lighting/patches.txt` |
| `tests/portal_unit/test_catalog_import.py` | `.github/workflows/ci.yml` (module list) |
| | `tools/fixture_builder/CATALOG.md` |

### 8.4 Step 1 — Permissions

In `portal_staff_permissions.py`:

1. Add `"ilL-Extrusion-Kit-Template"` to the template set in `authoring_permissions`
   (it is a product template like the others; this also gives `ilL Engineering`
   authoring on kits, which is consistent).
2. In `apply_service_permissions`, extend the Catalog Publisher matrix:

```python
	catalog_masters = {"read", "select", "write", "create", "report", "import", "export"}
	matrices["ilL Catalog Publisher"] = {
		**masters,
		"ilL-Webflow-Product": {...},            # unchanged
		"ilL-Webflow-Category": {...},           # unchanged
		"ilL-Webflow-Brand": {"read", "select"}, # unchanged
		# Catalog Builder imports run with the user's own permissions (owner decision 2026-10-05).
		**{name: set(catalog_masters) for name in ("Item", "Item Attribute", "Item Group", "UOM", "Brand", "Item Price")},
		"ilL-Catalog-Import": {"read", "select", "report"},
	}
```

   Do **not** grant `delete`. `Item Price` create lets catalog staff set prices — this
   is the owner's decision; mention it in the PR. `Price List`, `Currency` and
   `Supplier` stay read-only (they are only referenced, never created by catalogs).
3. New patch `illumenate_lighting/patches/catalog_builder_permissions.py`:

```python
"""Catalog Builder: Catalog Publishers create catalog masters with their own permissions."""


def execute():
	from illumenate_lighting.portal_staff_permissions import apply_staff_permissions

	apply_staff_permissions()
```

   Append `illumenate_lighting.patches.catalog_builder_permissions` at the end of the
   `[post_model_sync]` section of `patches.txt` (after the DocType below is synced, so
   `ilL-Catalog-Import` exists when permissions are applied).
4. Check `apply_staff_permissions` stays idempotent and does not remove permissions
   other roles rely on (it only manages the named roles). Run it twice on a bench.

### 8.5 Step 2 — Audit DocType `ilL-Catalog-Import`

Create it in Desk on a developer-mode bench (**DocType → New**, module
`ilLumenate Lighting`, not custom) so Frappe writes the JSON/py files, or hand-write
them by copying `ill_export_job`'s structure. Settings:

- Name `ilL-Catalog-Import`; folder `doctype/ill_catalog_import`; class `ilLCatalogImport`.
- `autoname: "format:CAT-IMP-{YYYY}-{#####}"`; not submittable; `track_changes: 0`;
  `allow_import: 0`; `sort_field: "creation"`, `sort_order: "DESC"`;
  `search_fields: "mode, status, series_name"`; `title_field: "series_name"`.
- Fields (all `read_only: 1`):

| fieldname | fieldtype | options / notes |
|---|---|---|
| `mode` | Select | `Check\nImport`; `in_list_view`, `in_standard_filter` |
| `status` | Select | `Passed\nFailed\nImported\nRolled Back\nRefused\nError`; `in_list_view`, `in_standard_filter` |
| `user` | Link | `User`; `in_list_view` |
| `product_type` | Data | |
| `series_name` | Data | |
| `catalog_hash` | Data | sha256 hex |
| `check_log` | Link | `ilL-Catalog-Import` (for Import: the passing Check it relied on) |
| `record_count` | Int | parent records in the catalog |
| `created_count` | Int | |
| `error_count` | Int | |
| `skipped_count` | Int | |
| `warning_count` | Int | |
| `duration_ms` | Int | |
| `section_payload` | Section Break | collapsible "Payload" |
| `catalog_json` | Code | `options: "JSON"`; the submitted catalog |
| `results_json` | Code | `options: "JSON"`; the `results` array |
| `error_detail` | Code | unexpected-exception traceback (System Manager only: `permlevel: 1`) |

- Permissions (JSON `permissions`): `System Manager` read/report/export/delete (+ permlevel 1 read);
  `ilL Catalog Publisher` read/report/export. **No create/write for anyone** — only the
  endpoint inserts, with `ignore_permissions=True` (the one allowed exception).
- Controller `ill_catalog_import.py`:

```python
from frappe.model.document import Document


class ilLCatalogImport(Document):
	pass
```

- `test_ill_catalog_import.py`: minimal `FrappeTestCase` stub like other DocTypes.
- Optional: list view indicator colours (`ill_catalog_import_list.js`): Passed/Imported
  green, Failed/Rolled Back/Error red, Refused orange.
- Add a workspace shortcut row `{"label": "Catalog Imports", "link_to": "ilL-Catalog-Import", "type": "DocType"}`
  plus a content block (new unique id), as in Session 1 Step 7.

### 8.6 Step 3 — Endpoints

All in `api/catalog_builder.py`. Contract details in Appendix A.

```python
import hashlib
import time

MAX_RECORDS = 500
CHECK_VALID_MINUTES = 30
SAVEPOINT = "ill_catalog_row"
LOCK = "ill_catalog_builder_import"


@frappe.whitelist(methods=["POST"])
def check(catalog):
	return _run(catalog, "Check")


@frappe.whitelist(methods=["POST"])
def import_catalog(catalog, expected_hash):
	return _run(catalog, "Import", expected_hash)


@frappe.whitelist(methods=["GET"])
def history(limit=20):
	require("catalog")
	limit = max(1, min(frappe.utils.cint(limit), 100))
	filters = {} if "System Manager" in frappe.get_roles() else {"user": frappe.session.user}
	return frappe.get_all(
		"ilL-Catalog-Import", filters=filters, limit_page_length=limit, order_by="creation desc",
		fields=["name", "mode", "status", "series_name", "product_type", "record_count",
			"created_count", "error_count", "skipped_count", "warning_count", "creation"],
	)
```

`catalog_hash`:

```python
def catalog_hash(catalog):
	text = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
	return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

The UI never computes it; it echoes the `catalog_hash` returned by a passing Check.

**`_run(catalog, mode, expected_hash=None)` — the pipeline.** It must never raise after
`require()` (see §3: an exception would roll back the audit log). Structure:

```python
def _run(catalog, mode, expected_hash=None):
	require("catalog")                                         # may raise 403: nothing written yet
	started = time.monotonic()
	catalog = frappe.parse_json(catalog) if isinstance(catalog, str) else catalog
	log = {"mode": mode, "user": frappe.session.user, "catalog_json": catalog}
	try:
		response = _guarded(catalog, mode, expected_hash, log)
	except Exception:
		frappe.db.rollback()
		log["error_detail"] = frappe.get_traceback()
		response = _response(mode, "Error", errors=["Unexpected server error. The run was rolled back; see the audit log."])
	finally:
		_release_lock()
	log.update(status=response["status"], duration_ms=int((time.monotonic() - started) * 1000))
	response["log"] = _write_log(log, response)                # inserts + commits
	return response
```

`_guarded` steps, in order:

1. **Shape.** `catalog` must be a dict with `records` dict of lists. Count parent records;
   if > `MAX_RECORDS` → `Refused` ("Split the catalog: N records, limit 500").
   Compute `digest = catalog_hash(catalog)`; `log["catalog_hash"] = digest`;
   copy `product_type`, `series_name`.
2. **Import gate** (mode Import only): `expected_hash == digest`, and a log exists with
   `mode="Check"`, `status="Passed"`, `user=session user`, `catalog_hash=digest`,
   `creation >= now - 30 min` (`frappe.utils.add_to_date(now_datetime(), minutes=-30)`).
   Else `Refused` ("Run Check again: the catalog changed or the check expired").
   Store the found check's name in `log["check_log"]`.
3. **Lock.** `frappe.db.sql("select get_lock(%s, 0)", f"{LOCK}:{frappe.local.site}")[0][0] == 1`,
   else `Refused` ("Another catalog check or import is running; try again shortly").
   One lock for Check and Import: a concurrent dry run could otherwise block on rows
   the import holds. `_release_lock()` runs `select release_lock(%s)` (safe if not held).
4. **Live existence map.**
   ```python
   schema = cached_schema()
   wanted = defaultdict(set)
   for doctype, rows in catalog["records"].items():
       if doctype not in schema["doctypes"]:
           continue                       # prepare_catalog reports it
       for row in rows:
           if isinstance(row, dict):
               if name := identity(doctype, with_defaults(doctype, row, schema), schema):
                   wanted[doctype].add(name)
               for target, value, _path in links(doctype, row, schema):
                   if target:
                       wanted[target].add(value)
   for doctype, names in catalog.get("external_links", {}).items():
       wanted[doctype].update(names)
   reference = {}
   for doctype, names in wanted.items():
       if frappe.db.exists("DocType", doctype):
           reference[doctype] = set(frappe.get_all(doctype, filters={"name": ["in", sorted(names)]}, pluck="name"))
   ```
   Query in chunks of 500 names if needed. Use `frappe.get_all` (not `get_list`) so the
   existence check is not narrowed by user permissions; the insert itself still checks
   permissions. Note: `prepare_catalog` treats a declared `external_links` name as
   existing **even if absent from `reference`**. Add an explicit check: every declared
   external link must be in `reference`, else error "Declared existing record not found
   in ERPNext: <DocType> <name>" (this catches the placeholder-name problem in §10.3).
5. **Validate.** `records, batches, external = prepare_catalog(catalog, schema, reference)`;
   on `ValueError as e` → `Failed`, `errors = str(e).splitlines()`, stage `validate`,
   nothing written. (These are the CLI's messages.)
6. **Permission pre-check.** For each DocType in `batches`:
   `frappe.has_permission(doctype, "create")`; collect "You cannot create <DocType>"
   errors; if any → `Failed`, stage `permissions`, nothing written.
7. **Insert.**
   ```python
   names = {}                         # (doctype, catalog-name) -> inserted name
   failed = set()                     # (doctype, catalog-name) of errored or skipped rows
   results = []
   for doctype, rows in batches:
       for row in rows:
           key = (doctype, identity(doctype, row, schema) or None)
           blocked = [f"{t} {v}" for t, v, _ in links(doctype, row, schema) if (t, v) in failed]
           if blocked:
               failed.add(key)
               results.append({..., "status": "skipped", "message": f"Depends on {blocked[0]}, which failed"})
               continue
           frappe.local.message_log = []
           frappe.db.savepoint(SAVEPOINT)
           try:
               doc = frappe.get_doc({"doctype": doctype, **row})
               doc.insert()
           except Exception as error:
               frappe.db.rollback(save_point=SAVEPOINT)
               failed.add(key)
               results.append({..., "status": "error", "message": _error_text(error)})
           else:
               frappe.db.release_savepoint(SAVEPOINT)
               results.append({..., "name": doc.name, "status": "created" if mode == "Import" else "checked",
                   "warnings": _messages()})
   ```
   - Do **not** pass `ignore_permissions`, `ignore_links`, `ignore_mandatory`.
   - `prompt`-named DocTypes (only `ilL-Attribute-LED Package` today) carry `name` in the
     row; `get_doc({... "name": ...})` sets it. Confirm with the bench test.
     `Item Price` has no autoname (hash); its result `name` is the generated hash.
   - `_error_text(error)`: prefer the last `frappe.local.message_log` entry's
     `message` (that is what `frappe.throw` shows), else `str(error)`; strip HTML with
     `frappe.utils.strip_html_tags`; cap at 1,000 chars; prefix the exception class for
     non-Frappe exceptions (e.g. `IntegrityError: Duplicate entry …`).
   - `_messages()`: messages left in `frappe.local.message_log` after a successful
     insert, HTML stripped, de-duplicated → `warnings`.
   - Each result row: `{"doctype", "catalog_name", "name", "status", "message", "warnings", "batch"}`
     where `batch` is the 1-based batch index (the UI groups by it).
8. **Finish the transaction.**
   - Check: always `frappe.db.rollback()`. Status `Passed` if no errors/skips, else `Failed`.
   - Import with any error/skip: `frappe.db.rollback()`, status `Rolled Back`.
   - Import with none: `frappe.db.commit()  # nosemgrep: commit the import before writing the audit log`,
     status `Imported`.
9. Build the response (Appendix A) and return; `_run` writes the log.

`_write_log(log, response)`:

```python
def _write_log(log, response):
	summary = response["summary"]
	doc = frappe.get_doc({
		"doctype": "ilL-Catalog-Import",
		**{k: v for k, v in log.items() if k != "catalog_json"},
		"catalog_json": json.dumps(log["catalog_json"], indent=1, ensure_ascii=False, default=str),
		"results_json": json.dumps(response.get("results", []), indent=1, ensure_ascii=False),
		"record_count": summary["records"], "created_count": summary["created"],
		"error_count": summary["errors"], "skipped_count": summary["skipped"],
		"warning_count": summary["warnings"],
	})
	doc.insert(ignore_permissions=True)          # audit log only; catalog records never bypass permissions
	frappe.db.commit()  # nosemgrep: the audit row must survive even though the run rolled back
	return doc.name
```

Edge cases to handle explicitly:

- `catalog` that is not a dict / unparsable JSON → `Refused` (still logged, with
  `catalog_json` as received, truncated to 100 KB).
- Empty `records` → `prepare_catalog` raises → `Failed` with its message.
- A record whose name already exists → `prepare_catalog` reports
  "already exists in ERPNext; remove this record and link to the existing one".
- Re-running Import after success → refused by the gate? No: the earlier passing Check
  still matches. It will fail at validation (all names now exist), which is correct;
  the UI also clears the Check after Import (Session 4).
- Very slow runs: log `duration_ms`; Session 5 decides about background jobs.

### 8.7 Step 4 — Tests

`tests/portal_unit/test_catalog_import.py` (bench-free; mock `frappe.get_doc` to return
objects whose `insert()` succeeds or raises; mock `frappe.db.sql` for the lock and
`frappe.get_all` for existence/logs). Required cases:

1. Non-catalog user → PermissionError, nothing written (`get_doc` not called).
2. > 500 records → `Refused`, log written, no inserts.
3. Validation error (unknown field) → `Failed`, stage `validate`, no `get_doc` for catalog DocTypes.
4. Declared external link missing from the site → `Failed` with the explicit message.
5. Missing create permission → `Failed`, stage `permissions`.
6. Check success → every row `checked`, `db.rollback()` called, `db.commit()` called
   only once (for the log), status `Passed`.
7. One failing row → that row `error`; a later row linking to it `skipped`; an
   unrelated later row still `checked`; status `Failed`.
8. Import without matching passing Check → `Refused`.
9. Import success → rows `created`, commit before log, status `Imported`, `check_log` set.
10. Import with an error → `Rolled Back`, `rollback()` called, no commit before the log.
11. Lock busy (`get_lock` returns 0) → `Refused`.
12. Unexpected exception inside the pipeline → `Error`, rollback, traceback in
    `error_detail`, lock released.
13. `catalog_hash` is stable across key order.

Bench test `illumenate_lighting/illumenate_lighting/api/test_catalog_import.py`
(add `--module illumenate_lighting.illumenate_lighting.api.test_catalog_import` to
`ci.yml`'s list):

- `setUp`: create a test user with role `ilL Catalog Publisher` (System User), and the
  minimum existing records a small catalog links to (Item Group, UOM `Nos`, the
  attribute records). Build the catalog in code from
  `tools/fixture_builder/templates/catalog_extrusion-kit.yaml` converted to JSON
  **with unique names** (prefix `ZZTEST-` plus a random suffix) so reruns don't collide.
  `frappe.set_user(test_user)`.
- Test: `check()` → `Passed`, and afterwards none of the catalog's records exist.
- Test: `import_catalog(catalog, check_hash)` → `Imported`, all records exist, log row
  exists with `created_count` = record count.
- Test: break one map row (unknown `lens_spec`) → `check()` `Failed`; `import_catalog` refused.
- Test: as a user **without** the role → PermissionError.
- `tearDown`: `frappe.set_user("Administrator")`; delete created records in reverse batch
  order; `frappe.db.rollback()` as appropriate for the test class.

### 8.8 Verification

§5.2 commands; bench test passes locally (or note why not). Manual call on a bench:

```bash
curl -s -X POST http://catalog.localhost:8000/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.check \
  -H "Content-Type: application/json" -H "Authorization: token <api_key>:<api_secret>" \
  -d @catalog.json | python -m json.tool
```

(API-key auth needs no CSRF token; browsers use the session cookie + CSRF header.)

### 8.9 Deploy notes

**Migrate** (new DocType JSON, `patches.txt`, workspace JSON). The patch applies
permissions on migrate. CI's upgrade job proves the patch runs from the base revision.

### 8.10 Out of scope

UI, background jobs, attachments, updates to existing records.

### 8.11 Risks to state in the PR

- ERPNext `Item` insert behaviour on the real site (defaults, naming, hooks that
  commit) is proven only in Session 5.
- `frappe.log_error` calls inside hooks write Error Log rows inside the transaction;
  they roll back with it (acceptable).
- Item Price create permission for Catalog Publishers (owner-approved).

---

## 9. Session 4 — Check/Import UI

**Goal:** in ERP mode, staff Check and Import from the builder and read results.

### 9.1 Starting-state check

Session 3 merged and deployed somewhere you can test (bench or staging). Endpoints
`check`, `import_catalog`, `history` respond.

### 9.2 Read first

`src/CatalogApp.jsx` (header actions, review aside, `message` and `confirm` patterns),
`src/catalog.css`, `src/erp-main.jsx`, `src/Workspace.jsx`, Appendix A.

### 9.3 Steps

**Step 1 — API client `src/erp-api.js`** (pure module, unit-testable):

```js
const BASE = '/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.';

export function createErpApi({ csrfToken, fetchImpl = fetch }) {
  async function call(method, { body, query } = {}) {
    const url = BASE + method + (query ? `?${new URLSearchParams(query)}` : '');
    const response = await fetchImpl(url, body ? {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Frappe-CSRF-Token': csrfToken },
      body: JSON.stringify(body),
    } : { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new ErpError(response.status, frappeMessage(data));
    return data.message;
  }
  return {
    reference: refresh => call('reference', { query: refresh ? { refresh: 1 } : undefined }),
    record: (doctype, name) => call('record', { query: { doctype, name } }),
    check: catalog => call('check', { body: { catalog } }),
    importCatalog: (catalog, expectedHash) => call('import_catalog', { body: { catalog, expected_hash: expectedHash } }),
    history: () => call('history'),
  };
}

/** Frappe errors: `_server_messages` is a JSON string of JSON strings. */
export function frappeMessage(data) { ... }   // parse _server_messages → messages; fall back to exception / exc_type
export class ErpError extends Error { constructor(status, message) { super(message); this.status = status; } }
```

On 401/403 show "Your ERPNext session has expired or you lack access. Reload the page
to log in again." with a link to `/login?redirect-to=/catalog-builder`. A CSRF failure
(`exc_type` `CSRFTokenError`) gets the same "reload" advice. Use this client for the
Session 1/2 reference/record calls too (refactor `erp-main.jsx` to create it once and
pass `api` down; drop the ad-hoc fetches).

**Step 2 — What is sent.** Send exactly the object the YAML download contains:
`resolved` (= `withReferenceLinks(catalog, schema, reference)`), minus
`add_to_reference` in ERP mode. Keep it in a `useMemo` (`payload`) and a
`payloadKey = JSON.stringify(payload)` to detect edits.

**Step 3 — State machine** (in `CatalogApp`, ERP mode only):

```
run = { phase: 'idle' | 'checking' | 'checked' | 'importing' | 'imported' | 'error',
        response, payloadKey }
```

- **Check in ERPNext** button (header, next to **Download catalog**): enabled when
  `issues.length === 0` and phase is not checking/importing. Sets `checking`, calls
  `api.check(payload)`, stores `{phase: 'checked', response, payloadKey}`.
- **Import to ERPNext**: enabled only when `run.phase === 'checked'`,
  `run.response.status === 'Passed'` and `run.payloadKey === payloadKey`. Any edit
  (payloadKey change) disables it and shows "Catalog changed since the last check — run
  Check again". Clicking opens the existing confirm modal (generalise its button label;
  today it says "Replace draft") with a per-DocType count, e.g.
  "Create in ERPNext: 5 Item, 1 Extrusion-Kit-Template, 4 Rel-Kit maps. This cannot be
  undone from the builder." Confirm → `importing` → `api.importCatalog(payload, run.response.catalog_hash)`.
- While checking/importing: disable Open YAML, Load example, Clear draft, product
  family switch, Check/Import; show a spinner and "Checking N records…".
- Network errors set `phase: 'error'` with the message; the editor stays usable.

**Step 4 — Results panel.** New component `ImportResults({response, onSelect})` rendered
full-width above the editor layout (or at the top of the review aside if space allows —
choose full-width; tables need room):

- Banner by status: `Passed` (green) "All N records passed. Nothing was saved —
  Import to create them."; `Failed` (red) "N problems. Nothing was saved.";
  `Rolled Back` (red) "Import stopped: N problems. Everything was rolled back —
  nothing was saved."; `Imported` (green) "Created N records in ERPNext.";
  `Refused` (orange) with the server message; `Error` (red) with the log name.
- Stage-level errors (`response.errors`, e.g. validation or permissions) as a list.
- Table grouped by `batch`, columns: Batch, DocType (`shortName`), Record, Status pill,
  Message / warnings. Record links to Desk only when `status === 'created'`:
  `/app/${slug(doctype)}/${encodeURIComponent(name)}` with
  `slug = d => d.toLowerCase().replace(/[^a-z0-9]+/g, '-')` (e.g. `ilL-Rel-Profile Lens`
  → `ill-rel-profile-lens`), `target="_blank" rel="noopener"`.
- Clicking a row with status error/skipped calls `onSelect(doctype, catalogName)`,
  which sets `selected` to that DocType and scrolls to the record whose
  `recordName(...) === catalogName` (add `id` attributes to record sections).
- Filter chips: All / Errors / Skipped / Warnings. Summary line with counts and
  duration. Link "Open audit log" → `/app/ill-catalog-import/<log>`.

**Step 5 — After Import.** On `Imported`: clear the run state, call
`api.reference(true)` to refresh existing records (the new records now show as
existing), and show a notice with **Start a new draft** (clears this product draft
after confirmation) explaining that re-checking this draft will now report duplicates.

**Step 6 — History.** In the review aside, a collapsible "Recent checks and imports"
loaded on open from `api.history()`: time, mode, status, series, counts, link to the log.

**Step 7 — Replace the CLI block in ERP mode.** The aside's "Generate the import
package" block becomes "Check and import in ERPNext" with one paragraph: Check is a
full dry run with ERPNext validation; Import is all-or-nothing; publication remains
separate (Readiness and Publication). Keep **Preview YAML** and **Download catalog**.

**Step 8 — Styles.** Extend `catalog.css` (scoped under `.catalog-app`): status pills,
banners, results table (sticky header, zebra rows), spinner. Keep contrast AA.

**Step 9 — Rebuild** `npm run build:erp`, commit the bundle.

### 9.4 Tests

- `tests/catalog.test.js` (or a new `tests/erp-api.test.js`): `frappeMessage` parses
  `_server_messages` (JSON-in-JSON), falls back to `exception`/`exc_type`; the client
  sends `X-Frappe-CSRF-Token` and JSON body on POST (inject `fetchImpl`); slug helper;
  per-DocType count helper.
- `render.mjs`: render `ImportResults` with fixture responses for `Passed`, `Failed`
  (with skipped rows), `Imported` (links present), `Refused`.
- Manual on bench/staging (record in PR): Check → Passed; edit → Import disabled;
  re-Check → Import → records openable in Desk; history shows both; break a link →
  errors shown, "nothing was saved".

### 9.5 Deploy notes

**Pull** update.

### 9.6 Out of scope

Server changes (except bug fixes found while integrating — call them out), attachments,
background jobs.

---

## 10. Session 5 — Staging rehearsal, production rollout, Vercel decision

**Goal:** prove the full flow on staging for every product family, fix what breaks,
document operations, roll out to production, and decide Vercel's future.

### 10.1 Ask the owner

- Which users get `ilL Catalog Publisher` on staging and on production.
- Confirm the staging URL (§1 note) and that staging was recently restored from
  production (so it has real records).
- Approval for each production step (deploy window, role assignment).

### 10.2 Deploy to staging

1. Merge Sessions 1–4 into `staging` (PR `main` → `staging`, or per the owner's flow).
2. Frappe Cloud → staging bench group → Deploy → **Update** the staging site
   (Migrate, because Sessions 1 and 3 touched hooks/DocType/patches/workspace).
3. Check the update log: patch `illumenate_lighting.patches.catalog_builder_permissions`
   executed; "Executing after_migrate hooks" without traceback; no new Error Log
   entries titled "ilL workspace preservation".
4. Open `https://stagingillumenate.v.frappe.cloud/catalog-builder` (§1 note) as
   Administrator: page loads, live reference loads, the Desk workspace shows
   **Catalog Builder** and **Catalog Imports** shortcuts.
5. Measure `reference` load time and payload size (DevTools). Target < 3 s, < 2 MB.

### 10.3 Role setup and permission proof

- Create or pick a non-admin System User; assign only `ilL Catalog Publisher`
  (plus `Desk User`/defaults as the site requires).
- In **Role Permissions Manager**, confirm create on: `Item`, `Item Attribute`,
  `Item Group`, `UOM`, `Brand`, `Item Price`, every `ilL-Spec-*`, `ilL-Attribute-*`,
  `ilL-Rel-*`, all seven templates including `ilL-Extrusion-Kit-Template`,
  `ilL-Webflow-Product`, `ilL-Webflow-Category`; read on `ilL-Catalog-Import`.
- As a Dealer and as a System User without the role: `/catalog-builder` → 403; the
  `check` endpoint → 403.

### 10.4 Build one real catalog per family

The shipped examples (`tools/fixture_builder/templates/catalog_*.yaml`,
`src/catalog-examples.json`) use **placeholder names that do not exist on the site**,
and the new declared-link check will (correctly) fail them:

| Example uses | Site has |
|---|---|
| `ilL-Attribute-Endcap Color: White` | `WH`, `BK`, `GR` |
| `ilL-Attribute-CRI: 90` | `90+`, `95+` |
| `ilL-Attribute-Output Voltage: 24V DC` | `24VDC` |
| `ilL-Attribute-LED Package: SW` | `ilLumenate Static White`, `ilLumenate Tunable White`, `ilLumenate Dim to Warm`, `ilLumenate RGBW`, `ilLumenate RGB+TW`, `ilLumenate Color Changing Pixel` |
| `ilL-Attribute-Power Feed Type: Single End Feed` | `Soldered-End` |
| `ilL-Spec-Driver: EXISTING-96W-DRIVER` | e.g. `PS-UNIV-24V-100W-IP66`, `PS-UNIV-24V-200W-IP66`, `PS-NON-24V-100W-IP66` |

Real anchors to link to (from the 2026-10-04 snapshot; confirm live):

| Family | Existing records to reuse | New records to create (prefix `ZZTEST-`) |
|---|---|---|
| Extrusion kit | Profiles `CH-CA01-WH/BK/SV`; lenses `LNS-CAXX-WH-WH/FR/CL/BK`; endcaps `EC-CA01-{WH,BK,GR}-{NO,HO}`; mounting `ACC-CAXX-MC`, `ACC-CA01-PV`; finishes `White`, `Black`, `Anodized Silver`; endcap colours `WH/BK/GR`; existing kit for comparison `KIT-CH02` | `ilL-Extrusion-Kit-Template` `ZZTEST-KIT-CA01` + its four maps |
| Linear fixture | Existing tape specs, profiles, lenses, drivers (see an existing template such as `ILL-AX01-SW`) | One `ilL-Fixture-Template` and its maps |
| LED tape / neon | Tape spec e.g. `LED-HD-DW-I-1830K-200-3M-WH-12MM`, template pattern like `cob-sd-sw` | One `ilL-Tape-Neon-Template` + offering + leader map |
| LED sheet | Spec e.g. `LED-SNF-SW-O-27K-10W-3M-WH`, template pattern `led-snf-sw` | One `ilL-LED-Sheet-Template` |
| Driver | Template pattern `PS-UNIV` | One driver spec + template |
| Controller | Spec/template pattern `DMXC-TW-BK-WALL` | One controller spec + template |

Note: `KIT-CA01` Items already exist but there is **no** `ilL-Extrusion-Kit-Template`
`KIT-CA01`. Creating the real one is a business decision for the owner, not part of
the rehearsal; use `ZZTEST-` names.

Optionally, in a **separate small PR**, update the example catalogs to real names so
"Load example" passes Check out of the box (regenerate `catalog-examples.json` with
`python -m tools.fixture_builder.catalog_examples`).

### 10.5 Rehearse each family (as the Catalog Publisher test user)

For each family: build the catalog → **Check** (Passed) → **Import** (Imported) →
open every created record from the results table → open the product in its
configurator and confirm it resolves:

| Family | Where to verify |
|---|---|
| Linear fixture | Portal `/portal/configure/<template>`; Desk Quotation → **Configure & Add Fixture** |
| LED tape / neon | `/portal/configure-tape`, `/portal/configure-neon` |
| LED sheet | `/portal/configure-sheet` |
| Extrusion kit | Fixture schedule kit line (kit configurator, `api/extrusion_kit_configurator.py`, `public/js/configurator/kit_steps.js`) |
| Driver / controller | Desk configurator flows that list drivers/controllers |

Then clean up: delete created records in **reverse batch order** (the results table
shows batches), or leave `ZZTEST-` records on staging and list them in the PR.

### 10.6 Transaction and failure proofs

1. Catalog whose **last** batch fails (e.g. a map referencing a non-existent spec, or a
   duplicate unique value): Import → `Rolled Back`; confirm in Desk that **no** record
   from earlier batches exists. If any do, something committed mid-request: search
   ERPNext and the app for `frappe.db.commit` reachable from `Item`/`ilL-*` insert
   (`grep -rn "db.commit" apps/erpnext/erpnext/stock/doctype/item apps/illumenate_lighting`),
   and fix by setting a flag the hook honours, or (last resort) switch Import to
   compensating deletes — document the choice in CATALOG.md.
2. Two browsers run Import at once → one gets "Another catalog check or import is running".
3. Edit after Check → Import disabled. Wait 31 minutes → Import refused by the server.
4. Session expiry (log out in another tab) → clear "log in again" message, no crash.
5. 500-record limit: a generated 501-record catalog → `Refused`.

### 10.7 Timing

Time Check and Import on the largest realistic catalog (a fixture family, ~30–60
records). If a run exceeds ~60 s, plan a follow-up to run `_run` via
`frappe.enqueue(queue="long")` with the audit DocType as the status record and UI
polling; do not build it in this session unless runs actually time out (Frappe Cloud
web requests time out around 120 s).

### 10.8 Security review

- Guest, Dealer, System User without role → 403 on page, `reference`, `record`,
  `check`, `import_catalog`, `history`.
- POSTs without `X-Frappe-CSRF-Token` → rejected.
- `record()` refuses DocTypes outside the catalog schema (e.g. `User`, `Sales Order`).
- No site data under `public/`: `grep -c '"exported_on"' illumenate_lighting/public/catalog_builder/catalog-builder.js` → 0.
- Catalog records are inserted without `ignore_permissions` (code search).
- Audit rows cannot be created or edited from Desk by Catalog Publishers.

### 10.9 Docs

- `tools/yaml_builder_ui/README.md`: ERPNext usage first (URL, role, Check/Import,
  results, history), then Vercel/CLI as the offline path.
- `tools/fixture_builder/CATALOG.md`: server import behaviour (all-or-nothing, per-record
  savepoints in Check, Check-before-Import gate, 500 limit, insert-only, attachments manual).
- `docs/B2B_STAFF_OPERATIONS.md`: operator checklist (build → Check → Import → verify in
  configurator → Readiness and Publication) and the role/permission list.

### 10.10 Vercel decision (ask the owner; record in README)

- **Keep (recommended):** offline drafting with the snapshot; no import there. Add a
  banner in Vercel mode: "To check and import, use the builder in ERPNext: <prod URL>/catalog-builder".
- **Retire:** delete the Vercel project; remove `vercel.json` and the README section;
  keep `npm run build` for local dev.

### 10.11 Production rollout

1. PR `staging` → `main` with the rehearsal evidence.
2. Owner picks a window; confirm a fresh backup.
3. Deploy the exact commit that passed staging; **Update** the production site (Migrate).
4. Repeat 10.2 step 3–4 and one extrusion-kit Check (no Import) on production.
5. Owner assigns `ilL Catalog Publisher` to the agreed users.
6. Watch the Error Log for an hour.
7. Rollback: restore the matched pre-update backup together with the previous app
   commit (never run old code on a migrated database).

### 10.12 Acceptance

Every family imported on staging from the builder with no CSVs; a failing Import
leaves no partial records; non-catalog users cannot reach page or endpoints; docs
updated; Vercel decision recorded; production updated and smoke-checked.

---

## 11. Appendix A — API contract

Base path: `/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.<fn>`.
All responses are Frappe-wrapped: `{"message": <payload>}`. All endpoints require
`ilL Catalog Publisher`, `System Manager` or `Administrator`; otherwise HTTP 403.

### `GET reference?refresh=0|1`

```json
{
  "schema_version": 1,
  "source": "live",
  "exported_on": "2026-10-05T14:03:11",
  "skipped": ["ilL-Some-DocType"],
  "doctypes": {
    "ilL-Attribute-Finish": {
      "source": "live",
      "exported_on": "2026-10-05T14:03:11",
      "records": { "White": { "finish_name": "White", "code": "WH", "status": "Active" } }
    }
  }
}
```

(Session 1 returns the committed snapshot in the same shape, `source` per DocType
`"export"`/`"links"`, plus `"unavailable": true` if the file is missing.)

### `GET record?doctype=<DocType>&name=<name>`

Returns the record reduced to schema fields, with child tables:
`{"profile_spec": "CH-CA01-WH", "compatible_lenses": [{"lens_spec": "LNS-CAXX-WH-FR", ...}], ...}`.

### `POST check` — body `{"catalog": {...}}`
### `POST import_catalog` — body `{"catalog": {...}, "expected_hash": "<sha256>"}`

Response (both):

```json
{
  "ok": true,
  "mode": "Check",
  "status": "Passed",
  "stage": "insert",
  "log": "CAT-IMP-2026-00012",
  "catalog_hash": "9f2c…",
  "summary": { "records": 9, "created": 0, "checked": 9, "errors": 0, "skipped": 0, "warnings": 1, "duration_ms": 2140 },
  "errors": [],
  "external": [["ilL-Attribute-Finish", "White"], ["Item Group", "Extrusion Kits"]],
  "results": [
    { "batch": 1, "doctype": "ilL-Extrusion-Kit-Template", "catalog_name": "ZZTEST-KIT-CA01",
      "name": "ZZTEST-KIT-CA01", "status": "checked", "message": "", "warnings": ["…"] }
  ]
}
```

| Field | Values |
|---|---|
| `status` | `Passed`, `Failed` (Check); `Imported`, `Rolled Back` (Import); `Refused`, `Error` (either) |
| `ok` | `true` only for `Passed` and `Imported` |
| `stage` | `shape`, `gate`, `lock`, `validate`, `permissions`, `insert` — where the run stopped |
| `errors` | run-level messages (validation, permissions, refusal); per-record problems are in `results` |
| `results[].status` | `checked`, `created`, `error`, `skipped` |
| `results[].name` | inserted name (generated for hash-named DocTypes); empty for error/skipped |

### `GET history?limit=20`

Array of `{name, mode, status, series_name, product_type, record_count, created_count, error_count, skipped_count, warning_count, creation}`,
newest first; System Managers see all users' runs, others their own.

### Error responses

Frappe error JSON with HTTP 403 (permission), 417 (validation thrown before the
pipeline, e.g. bad `record()` DocType), 400 (CSRF). Body may contain `exc_type`,
`exception`, and `_server_messages` (a JSON string of JSON strings, each with a `message`).

---

## 12. Appendix B — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/catalog-builder` shows the website header/footer and broken styles | Template lacks `</body>` so Frappe wrapped it | Keep the full HTML document (§3) |
| 404 on `/catalog-builder` | Route rule missing or site not migrated | Check `website_route_rules`; run a Migrate update |
| Blank page, console `IllCatalogBuilder is not defined` | Bundle not built/committed, wrong path, or cached old asset | `npm run build:erp`, commit; check `?v=` changes |
| Bundle is several MB | `erp-reference.json` reached the ERP entry | Remove every import of it from code reachable from `erp-main.jsx` |
| CI "bundle is fresh" fails | Bundle not rebuilt after a UI change, or non-deterministic build | Rebuild and commit; build twice locally to confirm identical output |
| `reference` returns `unavailable` (Session 1) | `tools/` not on the bench | Accept until Session 2 (live data) |
| `skipped` lists many DocTypes | Role lacks read | Session 3 permission patch not applied — run Migrate |
| Check says a declared record is missing | Placeholder or typo in `external_links` | Pick the live name from suggestions (§10.4 table) |
| Import refused "Run Check again" | Catalog changed, check older than 30 min, or different user | Re-run Check |
| "Another catalog check or import is running" | Lock held by a concurrent run | Wait; locks release when the request ends |
| Import `Rolled Back` but records exist afterwards | A hook committed mid-request | §10.6 step 1 |
| POST returns 400 `CSRFTokenError` | Stale page after re-login | Reload the page |
| Item insert errors about company/warehouse defaults | Site defaults missing (fresh bench) | Complete the setup wizard / Stock Settings |

---

## 13. Appendix C — Future work (not planned)

- Updating existing records from the builder (diff + merge with Desk edits).
- Attachment upload (spec sheets, images) as part of a catalog.
- Background import with realtime progress for very large catalogs.
- Using live `frappe.get_meta` (including site custom fields) for the browser schema
  instead of the repository DocType JSON.
- One-click hand-off from a successful Import to **Readiness and Publication**.
- Retiring `erp_reference.py` and the committed snapshot once Vercel is retired.
- Review whether `Dealer` should keep create/write on `ilL-Extrusion-Kit-Template`
  (its DocType JSON grants it today; spotted while writing this plan, unrelated to this feature).
