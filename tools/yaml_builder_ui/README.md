# ilLumenate YAML Builder

Author catalogs for **linear fixtures, LED tape, LED neon, LED sheets,
extrusion kits, drivers, and controllers** using the current ERPNext DocType fields.

## Use the builder in ERPNext

Open [Catalog Builder](https://illumenatelighting.v.frappe.cloud/catalog-builder),
or the **Catalog Builder** shortcut in the ilLumenate Lighting Desk workspace.
Log in with an enabled System User holding **ilL Catalog Publisher** or
**System Manager**; Administrator also has access.

Drafts are per browser and per site. Move them between ERPNext, Vercel, or devices
with **Save draft** and **Open YAML**. The ERPNext editor lists live records you can
read, cached for five minutes per user. Use **Refresh ERPNext records** after creating
or changing records in Desk. The loaded time uses the site's timezone; skipped
DocTypes appear under **No read access**. Existing DocType, record, and field
permissions apply. The Session 3 migration grants Catalog Publishers the catalog
create/import permissions and read-only audit access.

**Copy as new record** fetches the full readable record, including child rows and
long text, while omitting audit metadata, prices, supplier rows, and Webflow sync
state. Give the copy a new name before importing.

Use **Check in ERPNext** for a full dry run with live validation; nothing is saved.
A passing Check enables **Import to ERPNext** for that exact draft. Edits require
another Check, and a check expires after 30 minutes. Confirm the record counts to
import all records in one transaction. The results show errors, skipped dependencies,
warnings, and links to created records and the audit log. Select an error or skipped
record to return to its editor. **Recent checks and imports** shows your runs;
System Managers can see all runs.

After importing, start a new draft: the created names now exist in ERPNext. If an
import response is lost, review history and refresh existing records before trying
again; the request is never retried automatically. Reload and log in again if the
session or CSRF token expires. Publication remains a separate step through
Readiness and Publication.

Vercel and the CLI keep using the committed reference snapshot. ERPNext ignores
browser pending additions and `add_to_reference`; loaded drafts keep that flag
when saved for use with the CLI.

Rebuild the committed ERP bundle after editor changes:

```sh
npm ci --prefix tools/yaml_builder_ui
npm run build:erp --prefix tools/yaml_builder_ui
```

Commit both files in `illumenate_lighting/public/catalog_builder/`; CI rebuilds them
and checks freshness. The ERP build rejects imports of `erp-reference.json`, so
the public bundle contains only the editor, schema, and illustrative examples.
Deploy Session 4 with a **Pull** update after Sessions 1–3 have migrated. If deploying
the sessions together, use **Migrate** for the route, audit DocType, and permissions.

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
4. Resolve references by adding records, linking to a record in the live ERPNext list or Vercel snapshot
   (below), or selecting **Use existing ERPNext record**. That declaration does not
   verify the live site.
5. **Save draft** works anytime. **Download catalog** requires browser structure and
   reference checks to pass. **Open YAML** reopens version 2 YAML or JSON without
   discarding fields. Replacing a draft asks for confirmation.
6. In ERPNext, Check and then Import. For the Vercel/CLI workflow, run from the repository root:

```powershell
python -m tools.fixture_builder --config my-catalog.yaml --output ./output/my-catalog/
```

The CLI checks engineering values and variant ambiguity. Follow the generated
`IMPORT.md` and `manifest.json` to import the numbered CSVs in dependency order.
A DocType can have multiple batches when records depend on earlier records of that
type. Use only files named in the current manifest.

The ERPNext editor fetches live references and full copies, checks drafts, and imports
records into the site. Vercel keeps authoring local and exports YAML for the CLI.
Neither editor uploads attachments, publishes products, or creates orders.
Live ERPNext readiness remains authoritative for site records, compatibility
coverage, electrical selection, PDFs, and channel publication.

## Work in the record table

Each DocType opens as a table: one row per record, one column per field. The record
name column stays pinned while you scroll. Switch to **Cards** for the previous
one-card-per-record form.

- **More room:** **« Hide** the ERPNext records list to give the table the full width.
  **☰ ERPNext records** then opens it as a drawer that closes once you choose a
  DocType; **Pin** keeps it open beside the table. The choice is remembered.
- **Stay on track:** the bar above the table stays in view and shows badges as you
  edit: the current DocType's findings, and on **Import readiness** the checks to
  resolve (red), declared existing records not found (amber, `?`), a failed load of
  existing records (`!`) and, in ERPNext, whether the last Check failed or is out of
  date. A badge pulses when its count goes up; ✓ means ready. Each DocType in the list
  shows its own count.
- **Import readiness** opens as a dropdown with every readiness action: findings
  grouped by DocType (select one to jump to its cell, opening child tables and hidden
  columns on the way), unresolved links, declared records, the import command or
  ERPNext history, and the YAML preview. Escape or a click outside closes it.
- **Review:** each column header shows how many rows are filled (`3/10`). **Columns**
  hides fields or shows only fields with data (required fields always stay), and the
  field search above the table shows only matching columns. Choices and column widths
  (drag a header edge; double-click resets) are remembered per DocType in this
  browser. **Filter rows** finds records by any value.
- **Spreadsheet keys:** Tab, arrows and Enter move between cells. Shift+arrows,
  Shift+click or dragging selects a block; clicking a header or row number selects a
  column or row. Ctrl+C, Ctrl+X and Ctrl+V copy, cut and paste blocks, including to
  and from Excel or Google Sheets. Pasting one value into a block fills every selected
  cell, and pasting past the last row adds rows. Ctrl+D fills down, Delete clears, and
  Ctrl+Z / Ctrl+Y undo and redo any table change. **Shortcuts** lists them all.
- **Rows:** check rows (Shift+click checks a range), or select their cells, then
  **Duplicate**, **Insert row**, move them with ↑ / ↓, or **Delete** them. Duplicated
  records have their name cleared so you can give each copy a new one.
- **Child tables** show their row count; click one to edit its rows as a nested table
  under the record. Copying a child-table cell copies all its rows, so pasting it into
  another record's cell (or filling down) copies the child rows too. The ⤢ button
  opens a record as the full form with field descriptions.
- **Bulk entry:** **Copy table** copies the shown rows and columns with headers.
  **Paste rows** appends rows from spreadsheet cells on the clipboard, matching
  columns by header name when the first line has them.
- **Renaming keeps links:** edit a record's name in the table and, when you leave the
  cell, every field that links to the old name follows. That includes child rows,
  Dynamic Links, and records whose names are built from it: renaming Item `DEMO-TAPE`
  also renames its LED Tape spec, that spec's Tape Offerings, and the template rows
  linking those offerings. One Undo reverses the edit and its links. Links stay
  unchanged when another record still has the old name or already has the new one.
- **Find & replace** (Ctrl+H, or the button above the table) renames records or
  replaces text across the draft, in record names only or in every text and link
  field, for all DocTypes or the current one. Match case, whole value and regular
  expressions (`CH-(\w+)` → `PR-$1`) are available. The preview lists every change.
  Renames that would collide with a draft record or an existing ERPNext record start
  unchecked. Renamed records keep their links, as above. One Undo reverses it all.
- Cells with validation findings are shaded red and list the findings on hover; row
  numbers show a count of findings for the row, its child rows included. Links to
  existing ERPNext records have a green edge.

## Existing ERPNext records

For Vercel and the CLI, `src/erp-reference.json` is a snapshot of the records already in ERPNext, built from
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
  because Insert New Records would fail. A declared existing record absent from a
  complete reference list is flagged for review. In ERPNext, also check read access
  and refresh the list.

### Clone an existing family

**Clone existing family** (beside **Load example**) copies a family that is already in
ERPNext into the draft under new names. Pick a template (or a Webflow Product), then add
rename rules such as `CA01` → `CA03`. Rules apply in order to every name. Unless
**Match case exactly** is on, lowercase and uppercase matches keep their case, so
`ill-ca01-sw` becomes `ill-ca03-sw`.

- **What is copied:** every record whose name the rules change. That covers the
  template, its specs and Items, and the records that belong to them: endcap,
  mounting and kit maps, driver eligibility, tape offerings, leader cable maps,
  profile-lens maps, submittal mappings and Webflow products. Records that belong to
  another template are never pulled in, even when they share an Item.
- **What is linked:** records whose names stay the same. A copy can't keep its name,
  because it would collide with the original. Attributes, UOM, Item Group, Brand and
  Item Attribute are always linked.
- **Review** lists each record with what will happen and why. Switch a record to
  **Keep original** to link it instead of copying it; records named from it (a
  spec named by its Item) follow. When a new name already exists in ERPNext, the clone
  links to that record (**Use existing**).
- Links between the copies follow their new names, including child rows. A copied
  template's link to its copied Webflow product is cleared, because the pair would be
  circular on import; set it in ERPNext afterwards. Copies keep the original's values,
  including attachment URLs, so replace spec sheets and images.
- In ERPNext, records to copy are fetched in full, child rows included. A record that
  can't be read blocks the clone until you keep it as an original. On Vercel the
  export provides them, with only short fields for Webflow products.
- Records whose new name is already in the draft are skipped. **Replace the current
  draft** starts from an empty draft instead. Undo reverses the whole clone.

### Add a new catalog to the reference (Vercel and CLI)

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

Owner decision (2026-10-05): **keep Vercel for offline drafting**. The Vercel editor
links to the production ERPNext builder for Check and Import. Use **Save draft**
here and **Open YAML** in ERPNext; local browser drafts do not cross sites.

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

The ERP browser regressions use the repository's existing Playwright package and
controlled API responses (no site or credentials needed):

```sh
npm ci --prefix tests/portal_e2e
npm exec --prefix tests/portal_e2e -- playwright install chromium
npm run build:erp --prefix tools/yaml_builder_ui
npm run test:browser --prefix tools/yaml_builder_ui
```

Set `BROWSER_EXECUTABLE` to use an already installed Chromium. These tests cover
Check/Import gating, busy controls, error recovery, results, and history; also verify
the real Check → Import flow on an isolated bench before deploying.

Development refreshes the schema snapshot; production builds check it. To refresh
the shared examples, run `python -m tools.fixture_builder.catalog_examples` from the
repository root with PyYAML installed.

See the [catalog contract](../fixture_builder/CATALOG.md) for coverage, YAML format,
import behavior, and limits. The main files are `src/CatalogApp.jsx`, `src/RecordGrid.jsx`, `src/grid-model.js`,
`src/catalog-model.js`, and `tools/fixture_builder/catalog.py`.
