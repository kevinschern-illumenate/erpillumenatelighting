# ilLumenate YAML Builder

Author catalogs for **linear fixtures, LED tape, LED neon, LED sheets,
extrusion kits, drivers, and controllers** using the current ERPNext DocType fields.

## Use the builder in ERPNext

Open [Catalog Builder](https://illumenatelighting.v.frappe.cloud/catalog-builder),
or the **Catalog Builder** shortcut in the ilLumenate Lighting Desk workspace.
Log in with an enabled System User holding **ilL Catalog Publisher** or
**System Manager**; Administrator also has access.

Drafts are per browser and per site. Move them between ERPNext, Vercel, or devices
with **Save draft** and **Open YAML**. This release reads the committed ERPNext
snapshot through an authenticated endpoint; live records arrive in the next release.
If the snapshot is unavailable, declare existing records manually. Generate CSVs
with the CLI and import them through ERPNext Data Import as described below.
The Vercel workflow is unchanged.

Rebuild the committed ERP bundle after editor changes:

```sh
npm ci --prefix tools/yaml_builder_ui
npm run build:erp --prefix tools/yaml_builder_ui
```

Commit both files in `illumenate_lighting/public/catalog_builder/`; CI rebuilds them
and checks freshness. The ERP build rejects imports of `erp-reference.json`, so
the public bundle contains only the editor, schema, and illustrative examples.
Deploy this hosting release with a **Migrate** update for the route and workspace
shortcut. A missing snapshot reports unavailable until the live-data release.

## Start

```powershell
cd tools/yaml_builder_ui
npm install
npm run dev
```

The default catalog editor supports Item masters, engineering specs, templates,
variants, child options, attributes, compatibility maps, cable maps, driver
eligibility, certifications, submittal mappings, pricing, and Webflow product data.
Fields and choices come from the repository DocType JSON, including nested tables.
Use **Family expansion editor** for the existing fixture/tape/neon wizard.

## Author and generate

1. Select a product family. Each family keeps its own draft in browser storage.
2. Add records or load an illustrative example. Replace example engineering ratings
   and review every declared existing ERPNext record before using the example.
3. Enter linked names. Suggestions include catalog records and declared existing
   records. Create missing Item records, then set their Item Group and UOM.
4. Resolve references by adding records, linking to a record in the ERPNext export
   (below), or selecting **Use existing ERPNext record**. That declaration does not
   verify the live site.
5. **Save draft** works anytime. **Download catalog** requires browser structure and
   reference checks to pass. **Open YAML** reopens version 2 YAML or JSON without
   discarding fields. Replacing a draft asks for confirmation.
6. From the repository root, run:

```powershell
python -m tools.fixture_builder --config my-catalog.yaml --output ./output/my-catalog/
```

The CLI checks engineering values and variant ambiguity. Follow the generated
`IMPORT.md` and `manifest.json` to import the numbered CSVs in dependency order.
A DocType can have multiple batches when records depend on earlier records of that
type. Use only files named in the current manifest.

The ERPNext editor fetches the reference snapshot from the site. Both editors
keep authoring local; they do not import records, upload attachments, publish products,
or create orders. Live ERPNext readiness remains authoritative for site records, compatibility
coverage, electrical selection, PDFs, and channel publication.

## Existing ERPNext records

`src/erp-reference.json` is a snapshot of the records already in ERPNext, built from
ERPNext's DocType exports: LED Tape specs, profiles, lenses, accessories, drivers,
templates, attributes, relationship maps, and every Item (templates and variants,
with their variant attributes), plus the Item Groups, UOMs, Brands and Item
Attributes those records link to. In the editor:

- Link fields suggest existing records with their key values, and show
  **Existing ERPNext record** when a link matches one, so a new fixture family can
  use an existing LED Tape spec instead of re-creating it.
- Links to existing records resolve automatically and are written to the
  downloaded YAML's `external_links`, so the import package does not re-create them.
- Each DocType page lists its existing records. Search them, or **Copy as new record**
  to start from an existing spec or template.
- Adding a record whose name already exists in ERPNext is a validation finding,
  because Insert New Records would fail. A declared existing record that a fully
  exported DocType does not contain is flagged as a likely typo.

### Add a new catalog to the reference

Check **Add to ERPNext reference after import** when the catalog will be imported.
The YAML then carries `add_to_reference: true` (the catalog needs a name):

- On **Download catalog**, its records count as existing ERPNext records for your
  other catalogs in this browser, marked *Pending import*.
- When the CLI generates the import package, it adds the records to
  `src/erp-reference.json` and logs the catalog under `catalog_additions`. Import the
  package, then commit that file so every builder user can link to the new records.
- Rebuilding the same catalog does not report its own records as already existing;
  any other catalog that re-creates them is stopped.
- Pending entries disappear once the deployed reference includes the catalog, or
  use **Remove from this browser**. A later export rebuild replaces the additions
  with the records as ERPNext holds them.

Prices and costs, Item supplier rows, audit fields, and Webflow sync state are not
stored. DocTypes that were not exported (such as UOM and Item Group) only list names
that exported records link to.

To refresh it, export each DocType in ERPNext (**Menu → Export**, all records, with
child tables), zip the CSVs, and run from the repository root:

```powershell
python -m tools.fixture_builder.erp_reference DocType_Exports.zip
```

To refresh only some DocTypes, export just those and add `--update`; the others and
any catalog additions are kept:

```powershell
python -m tools.fixture_builder.erp_reference Item.csv --update
```

The CLI reads the same snapshot; pass `--no-reference` to ignore it.

## Host on Vercel

The builder is a static site: drafts stay in each browser's storage and exports are
browser downloads, so it needs no server or ERPNext access.

1. In Vercel, choose **Add New → Project** and import this GitHub repository.
2. Set **Root Directory** to `tools/yaml_builder_ui`. Keep **Include files outside
   the root directory in the Build Step** enabled; the build checks the schema
   snapshot against `illumenate_lighting/**/doctype` JSON.
3. Leave the build settings alone. `vercel.json` runs the schema check, the tests,
   and `vite build`, then serves `dist/`.
4. Deploy. Pushes to the production branch redeploy automatically; other branches
   get preview URLs.

To limit who can open it, enable **Settings → Deployment Protection → Vercel
Authentication** (or Password Protection) for all deployments. Drafts are per browser
and per URL, so use **Save draft** to move work between devices. Run the CLI
locally on the downloaded YAML as described above.

To deploy from a terminal instead, set the Root Directory in the dashboard first,
then run `npx vercel link` and `npx vercel --prod` from the repository root.

## Keep fields current

```powershell
npm run schema
npm run schema:check
npm test
npm run test:render
npm run build
```

Development refreshes the schema snapshot; production builds check it. To refresh
the shared examples, run `python -m tools.fixture_builder.catalog_examples` from the
repository root with PyYAML installed.

See the [catalog contract](../fixture_builder/CATALOG.md) for coverage, YAML format,
import behavior, and limits. The main files are `src/CatalogApp.jsx`,
`src/catalog-model.js`, and `tools/fixture_builder/catalog.py`.
