# ilLumenate YAML Builder

Author catalogs for **linear fixtures, LED tape, LED neon, LED sheets,
extrusion kits, drivers, and controllers** using the current ERPNext DocType fields.

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
4. Resolve references by adding records or selecting **Use existing ERPNext record**.
   That declaration does not verify the live site.
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

The editor does not contact ERPNext, upload attachments, publish products, or create
orders. Live ERPNext readiness remains authoritative for site records, compatibility
coverage, electrical selection, PDFs, and channel publication.

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
