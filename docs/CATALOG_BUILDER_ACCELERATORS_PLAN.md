# Catalog Builder accelerators: plan

Five additions to the YAML / Catalog Builder (`tools/yaml_builder_ui`, the v2 catalog
in `catalog_authoring/catalog.py`, and `api/catalog_builder.py`) aimed at one goal:
onboard a whole product family in minutes instead of hand-typing every record.

Today a new fixture family means typing every Item, spec, endcap / mounting / driver /
leader map row by hand, one draft per product type, with **Copy as new record** one
record at a time, and finding out that the family doesn't fully configure only after
it's imported. The features below go after those costs.

| # | Feature | Saves | Size | Depends on |
|---|---------|-------|------|------------|
| 1 | Rename with link propagation + Find & replace | Fixing names everywhere by hand | S | — |
| 2 | Clone an existing family | Re-creating 15–40 records per family | M | 1 |
| 3 | Row generator (option matrix) | Typing every map/Item permutation | L | 1 |
| 4 | Coverage preflight ("Will it configure?") | Post-import Desk fixes | M–L | 3 for "Generate missing" |
| 5 | Draft library + ERPNext draft sync | Save/Open YAML shuffling; one draft per type | M | — |

Suggested order: **1 → 2 → 3 → 4 → 5**. Each lands as its own PR with tests,
README/CATALOG.md updates, and a rebuilt ERP bundle (`npm run build:erp`, commit
`illumenate_lighting/public/catalog_builder/`).

---

## 1. Rename with link propagation + Find & replace

**Problem.** Changing `CH-CA01` to `CH-CA02` in the Item table leaves every
spec, template, map and child row still pointing at `CH-CA01`, so the draft fills
with unresolved links. There is no bulk find/replace.

**What you get.**
- Edit a record's name cell (the `field:` naming field, or `name`) and the builder
  updates every Link / Dynamic Link / child-row link to it in the same undo step.
  A status line says "Renamed CH-CA01 → CH-CA02 and updated 14 links". Records named
  by `format:` rules (endcap, mounting, driver, leader maps) follow automatically,
  because their names are computed from the renamed links.
- **Find & replace** (toolbar, Ctrl+H): text or regex; scope = names only / all text
  fields / chosen DocTypes; case-sensitive toggle. A preview table lists every change
  (DocType, record, field, before → after) with checkboxes. Renamed names propagate
  to links exactly as above. One undo step.
- Collision guard: a rename onto a name that already exists in the draft or in the
  ERPNext reference is shown in the preview and skipped unless unchecked.

**Implementation.**
- `src/catalog-model.js`
  - `linkTargets(schema)`: per DocType (including child DocTypes), the fields that link
    to which DocType, with Dynamic Link resolution via the sibling type field.
    Built once from `schema.doctypes` (memoize on the schema object).
  - `renameRecords(catalog, schema, renames)` where `renames` is
    `[{doctype, from, to}]`: sets the naming field on the matched record, then walks
    every record and child row (reuse the traversal in `linkedRecords`) and rewrites
    matching link values. Also rewrites `external_links[doctype]` entries. Returns
    `{catalog, changed: [{doctype, record, path, from, to}]}`. Pure; no mutation.
  - `findReplace(catalog, schema, {find, replace, regex, caseSensitive, scope, doctypes})`:
    returns the planned change list; name-field changes are routed through
    `renameRecords` so links follow.
- `src/RecordGrid.jsx`: when a commit changes the naming column, call an
  `onRename(doctype, from, to)` prop instead of a plain `replaceRow`.
- `src/CatalogApp.jsx`: `onRename` → `setCatalog(renameRecords(...), {label: 'Rename'})`;
  new `FindReplaceDialog.jsx` (reuse `ConfirmDialog` styling) and Ctrl+H binding next to
  the existing shortcuts; add to the **Shortcuts** list.
- No server change: the server receives already-renamed catalogs.

**Tests.** `tests/catalog.test.js`: rename propagates through a top-level Link, a
child-table Link, a Dynamic Link (`ilL-Rel-Driver-Eligibility.fixture_template`),
`external_links`, and changes a `format:` name; collision is reported; regex replace
of a series code across Item codes + template codes; undo restores the original.

---

## 2. Clone an existing family

**Problem.** Most new families are near-copies of an existing one (a new profile in
an existing series, a new tape with the same offerings). **Copy as new record** works
one record at a time and doesn't bring along the maps that point *at* the template.

**What you get.**
- **Start from existing family** on the product bar. Pick a template (Fixture /
  Tape-Neon / LED Sheet / Extrusion Kit / Driver / Controller) or a Webflow Product
  from the reference list (live in ERPNext, snapshot on Vercel).
- The builder gathers the family: the template, everything it links to, and the
  records that point back at it (endcap / mounting / driver-eligibility maps,
  leader-cable maps for its tape specs, profile-lens maps for its profile specs,
  finish-endcap colors) — the same relationships `product_readiness.related_dependencies`
  already knows about.
- A review screen groups them into **Copy as new** (family-specific: template, its
  specs, its Items, its maps, its Webflow product) and **Link existing** (shared:
  attributes, series, drivers, UOM/Item Group, LED tape specs used elsewhere). Each row
  can be flipped. Shared/unique is decided by whether anything outside the family also
  links to the record.
- A **rename map** (`CA01 → CA02`, `Castle → Keep`) previews every new name; it runs
  feature 1's engine, so all links follow. Names that would collide with ERPNext are
  flagged before anything is written.
- **Add to draft** (merges into the current draft) or **Replace draft**.

**Implementation.**
- `src/catalog-model.js`
  - `familyGraph(reference, schema, root, {maxRecords: 200, maxDepth: 6})`: BFS over the
    reference. Outbound edges from `linkTargets`; inbound edges from an index of
    "who links to (doctype, name)" built from the reference records (they keep Link
    fields; Item is summary-only but keeps its Links). Stop expanding at shared master
    DocTypes (attributes, UOM, Item Group, Brand, Series, Driver specs) — include them as
    link-existing leaves.
  - `classifyFamily(graph, reference)`: copy vs. link, using inbound edges from outside
    the graph.
  - `cloneFamily(catalog, schema, graph, choices, renames)`: copies chosen records
    (`asNewRecord`-style, but keeping names so `renameRecords` can rewrite them), adds
    link-existing records to `external_links`, applies renames, strips audit/price/
    Webflow sync fields exactly as `referenceRecord` does.
- ERPNext mode: full records come from the existing `api.record(doctype, name)`
  (already used by **Copy as new record**), fetched with a small concurrency limit
  (4) and a progress line. Add `api/catalog_builder.py::family(doctype, name)` only
  if the client-side graph proves too slow on the live reference; it would reuse
  `product_readiness.dependency_manifest` bounds and `reference_record`.
- Vercel mode: snapshot records are used as-is (Items are summary-only there, so the
  review screen notes "Item details limited to the export").
- New `src/CloneFamilyDialog.jsx`; entry button in `CatalogApp.jsx`.

**Tests.** Clone the shipped fixture example's records from a synthetic reference:
inbound endcap/mounting/driver maps are found; drivers and attributes land in
`external_links`; rename `CA01→CA02` leaves zero unresolved links and zero
`catalogIssues`; a name colliding with the reference is flagged; graph bounds stop at
200 records with a visible notice. Python: if `family()` is added, an installed-site test
mirroring `test_catalog_import.py`.

---

## 3. Row generator (option matrix)

**Problem.** The bulk of a family is permutations: profile Items per finish, lens
Items per appearance, endcap maps per style × color, mounting maps per method,
driver eligibility per driver, leader cable maps per tape spec × feed. The legacy
**Family expansion editor** knew these conventions, but it is separate from the v2
editor and its fields lag the DocTypes.

**What you get.**
- **Generate rows** button on every DocType table. Dialog:
  1. **Axes**: each axis is a list of values — typed, pasted, picked from an
     attribute DocType (`ilL-Attribute-Finish`, etc., from draft + reference), or
     taken from the draft template's `allowed_options` rows (filtered by
     `option_type`). Each value exposes its fields as tokens (`{finish}`,
     `{finish.code}`).
  2. **Field patterns** for the target DocType: every column can be a constant, a token
     pattern (`CH-{profile}-{finish.code}`), or blank. Required fields are listed first.
  3. **Preview** the cartesian product as a read-only grid with findings inline;
     existing names are marked "already in draft" / "exists in ERPNext" and skipped.
  4. **Add N rows** (one undo step).
- **Presets** per product type pre-fill axes and patterns from the draft:
  - Fixture: *Profile Items by finish*, *Lens Items by appearance*,
    *Endcap map from allowed options* (template × endcap style × endcap color via
    `ilL-Rel-Finish Endcap Color`), *Mounting map from allowed mounting methods*,
    *Driver eligibility for drivers…*, *Leader cable map for tape specs × feed types*.
  - Tape / neon / sheet / kit / driver / controller: their map and Item equivalents.
- **Saved recipes**: save a configured generator as a named recipe (browser storage,
  and in the YAML under a new optional top-level `builder:` key so it travels with
  **Save draft**).

**Implementation.**
- `src/generator-model.js` (new, pure): `axisValues(axisSpec, catalog, reference, schema)`,
  `expandPattern(pattern, binding)`, `generateRows(doctype, schema, axes, patterns)`,
  `dedupe(rows, catalog, reference, schema)`, `presets[productType]`.
- `src/GenerateRowsDialog.jsx` (new) using `RecordGrid` read-only for the preview.
- `catalog_authoring/catalog.py`: accept and ignore a `builder` top-level key (it is
  currently rejected as "Unknown catalog key"). The client strips `builder` before
  Check/Import, like `add_to_reference`, so recipe edits don't change `catalog_hash`.
  `parseCatalog` accepts it; CLI ignores it.
- Retire nothing yet: link the legacy editor's README section to the presets and decide
  later whether to remove the Family expansion editor.

**Tests.** `tests/generator.test.js`: cartesian expansion, dotted tokens, constant vs.
pattern fields, dedupe against draft and reference, each preset on the shipped
examples produces rows with zero new `catalogIssues`, `builder` round-trips through
YAML and is stripped from the Check payload. Python: `builder` accepted by
`prepare_catalog`, absent from CSV output.

---

## 4. Coverage preflight ("Will it configure?")

**Problem.** Check proves the records insert, not that the product configures. An
allowed endcap style with no endcap map row, or a mounting method with no accessory
map, only surfaces later in `guardrail_audits.run_coverage_audit`, readiness, or a
failed configuration.

**What you get.**
- A **Coverage** group in **Import readiness**, live as you edit, per template:
  - allowed endcap style × endcap color (via finish → endcap color) × feed type without
    an endcap map row;
  - allowed mounting methods without a mounting accessory map;
  - tape specs × allowed feed types without a leader cable map;
  - empty tape offering whitelist; no driver eligibility rows; no Webflow product.
  Amber (warning) badges, not blocking. Each gap has **Generate missing rows**, which
  opens feature 3's dialog pre-filled with exactly the missing combinations.
- **Check in ERPNext** additionally runs, inside the rolled-back transaction after the
  inserts succeed: the server coverage audit for each new fixture template and a
  smoke configuration per template (default options, a short length) through the
  real configurator. Results appear as a **Configurability** section in the Check
  results. Warnings do not block Import (an option to make them blocking can come
  later).

**Implementation.**
- `src/coverage-model.js` (new, pure): `coverageGaps(catalog, schema, reference)`
  returning `[{template, kind, missing: [{...combination}], doctype}]`. Rules mirror
  `_check_endcap_map_coverage`, `_check_mounting_map_coverage`,
  `_check_leader_map_coverage` in `api/guardrail_audits.py`; Python stays authoritative.
- `src/CatalogApp.jsx`: add the group to the readiness dropdown and badge count;
  **Generate missing rows** → `GenerateRowsDialog` with explicit rows.
- `api/catalog_builder.py::_guarded`: when `mode == "Check"` and no row failed, call
  a new `_configurability(results)` before `frappe.db.rollback()`. It runs
  `guardrail_audits._audit_template(name)` for inserted fixture templates and a
  per-family smoke resolve (fixture / tape-neon / LED sheet configurator entry points),
  each in its own savepoint and try/except so a crash becomes a warning, never a
  failed Check. `_response` gains a `configurability` list stored on the
  `ilL-Catalog-Import` receipt (new JSON field, migration) and returned to the client.
- `src/ImportResults.jsx`: render `configurability`.

**Tests.** JS: each gap kind detected on a trimmed fixture example and cleared after
generating the missing rows. Python (installed-site, alongside
`test_catalog_import.py`): a Check with a missing endcap map passes with a coverage
warning; a complete example reports clean coverage and a successful smoke resolve;
nothing persists after Check. Browser test: the Configurability section renders.

---

## 5. Draft library + ERPNext draft sync

**Problem.** The builder keeps exactly one draft per product type in one browser
(`illumenate-product-catalog-v2` → `drafts[productType]`). Working two fixture
series at once, or moving between laptop and desk, means **Save draft** / **Open YAML**
by hand, and an accidental **Clear draft** beyond 100 undo steps is gone.

**What you get.**
- A **Drafts** menu: list of named drafts (name, product type, record count, issues,
  last edited), **New**, **Duplicate**, **Rename**, **Delete** (confirm), and **Open YAML**
  into a new draft instead of replacing the current one.
- **Versions**: an automatic snapshot every few minutes of editing and before every
  destructive action (Load example, Clear, Replace, Import); the last 20 per draft
  can be previewed and restored.
- **In ERPNext**: drafts save to the site (per user, private), so the same draft
  opens on any device. A "Saved to ERPNext · 10:42" indicator; conflicts (edited in
  two tabs) offer "keep mine / keep theirs / save as copy". Vercel stays
  browser-only.
- Import receipts link back to the draft they came from.

**Implementation.**
- Storage model: `{version: 3, active: draftId, drafts: {[id]: {id, name, product_type,
  catalog, updated, versions: [...]}}}`; migrate `v2` (one per product) to one named
  draft per non-empty product on first load, keeping the old key until the next
  successful save.
- `src/draft-store.js` (new): `listDrafts`, `saveDraft`, `snapshot`, `restore`, with a
  `local` backend (localStorage, quota-aware: drop oldest versions first) and an `erp`
  backend.
- Backend: new DocType `ilL-Catalog-Draft` (`title`, `product_type`, `catalog_json`
  Long Text, `revision` Int, owner-only permission via `has_permission` hook) and
  `api/catalog_builder.py` methods `drafts()`, `draft(name)`, `save_draft(name, title,
  catalog, revision)` (optimistic concurrency on `revision`), `delete_draft(name)`.
  Patch grants **ilL Catalog Publisher** create/read/write/delete on own drafts.
- `src/CatalogApp.jsx`: replace `restore()` / `workspace.drafts[active]` with the
  store; history (undo) stays per draft in memory.
- `src/erp-api.js`: the four draft calls (saves debounced 2s; POST still never
  auto-retried).

**Tests.** JS: v2 → v3 migration, version cap and quota fallback, conflict on stale
revision. Python installed-site: owner isolation (another publisher can't read or
overwrite), revision conflict, size limit. Browser: switch drafts, restore a version.

---

## Considered, not chosen (yet)

- **Update existing records** (import changes to records already in ERPNext, e.g. add
  a finish to a live template). High value, but it breaks the deliberate insert-only
  guarantee of Check/Import and needs diff review, field-level permissions and
  rollback semantics. Worth its own plan after these land; feature 2's family graph
  and feature 5's versions are useful groundwork.
- **Spreadsheet import of supplier datasheets**: largely covered by the existing
  **Paste rows** with header matching.

## Cross-cutting checklist per PR

- `npm test`, `npm run test:render`, `npm run build`, `npm run build:erp` (commit the
  bundle), `npm run test:browser` when ERP UI changes.
- `python -m unittest discover -s tools/fixture_builder/tests -q`; installed-site tests
  for server changes; `ruff check .` and `ruff format .`.
- Update `tools/yaml_builder_ui/README.md` and `tools/fixture_builder/CATALOG.md`.
- Server changes (features 4 and 5) need **Migrate** on deploy; UI-only ones need **Pull**.
