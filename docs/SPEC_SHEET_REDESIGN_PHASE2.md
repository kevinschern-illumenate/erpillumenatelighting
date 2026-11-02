# Spec Sheet Redesign: Phase 2 (template-first spec data)

Plan: `erpnext_spec_sheet_redesign_plan.md` Phase 2, with the owner decisions in the Phase 0 and 1a notes.
Done in three pushes so each can be checked on staging:

- **2a**: templates calculate and store their specification rows and configurator steps; products
  merge in what the template owns; the D43 rules. (This push.)
- **2b**: `get_spec_sheet_data` (payload v2 with the `legacy` adapter) and the field ownership table.
- **2c**: everything that reads the product's `configurator_options` reads the template's
  `part_no_configurator` instead, then the product table is removed (owner, 2026-11-02).

## 2a: how it works

The product calculations (`sync_custom_template_data`, the six `populate_*_configurator_options`
methods) only read the linked template. They now load it through `_template_doc()`, which returns
an in-memory template when one is supplied, and take "Is Required" choices from
`flags.existing_is_required` when supplied.

`template_listing.py`:

- `shadow_product(template)`: an unsaved Webflow Product that points at the template being saved.
- `compute(template)`: runs the product code on the shadow and returns its specification rows
  and configurator steps. Because it is the same code, a template's rows match its product's.
- Template `validate`: `refresh_template` stores the result in `specifications` and
  `part_no_configurator`. Rows typed on the template (labels that are not calculated) are kept. A
  calculation error never blocks the save: the old rows stay and the user sees a message.
- Template `on_update`: `push_to_product` saves the linked product (D21). A product that cannot be
  saved is reported, never blocks the template save. No recursion: product saves never save the
  template.
- Product `before_save` (end): `apply_template_rows`. The product keeps its own fresh calculated rows
  (stored template rows can be older than a changed tape spec or attribute record), and takes from
  the template what people decide there: hand-typed specification rows and each configurator step's
  "Is Required". Rows typed on the product by hand are kept.

D43, everywhere the calculation runs (template and product):

- A row whose value is the placeholder "TBD" is not added (the driver rows and the LED Sheet
  "Dimming" row).
- An operating temperature range of 0 to 0 is treated as "not set" and not added (kits and LED
  sheets; it showed as "32°F (0°C) to 32°F (0°C)").

Also: the calculation wrote an Error Log ("Combined Full Enrichment Debug") on every product save.
It now does so only when site config `webflow_enrichment_debug` is set.

## 2a: checks on staging

1. Deploy. Nothing changes until a template or product is saved.
2. Compare what each linked template would store with what its product holds today (read-only):

   ```python
   import json
   from illumenate_lighting.illumenate_lighting.template_listing import compare_listing
   print(json.dumps(compare_listing(), default=str, indent=1))
   ```

   It compares the template's calculation with the product's own calculation run in memory on
   today's data (what the product would hold after its next save), not with the product's stored
   rows, which are often older.

   - `with_unexpected_differences` should be empty. Any difference there is a bug to fix first.
   - `expected_only` counts products whose only differences are the D43 rows.
   - `stale_products`: products whose stored rows are older than their own calculation. They
     change on their next save whatever the template does. Information only.
   - `hand_curated_configurators`: products with "Auto Populate Configurator Options" off, whose
     steps were set up by hand. The template never changes them (not even "Is Required"); what
     happens to them when the product table goes is decided in 2c.

   The first staging run compared against stored rows, so almost every product showed
   differences (old number formats, old environment codes, rows never recalculated). That run
   also showed that hand-set Tape/Neon configurators use different step numbers, so copying the
   template's "Is Required" by step would have changed the wrong steps. Fixed before any template
   was saved.
3. Store the rows on every template (products update on their next save):

   ```python
   import json
   from illumenate_lighting.illumenate_lighting.template_listing import refresh_all_templates
   print(json.dumps(refresh_all_templates(apply=True), default=str, indent=1))
   ```

   `failed` lists templates whose save failed, with the reason.

## 2a: result on staging (2026-11-02)

`compare_listing`: 82 linked templates, no unexpected differences. 71 products hold stored rows
older than their own calculation (they update on their next save); 55 have configurator steps set
up by hand. `refresh_all_templates(apply=True)`: 230 templates saved, none failed.

## 2c, first push: readers take the template's configurator

Done in two pushes. This one moves every reader to the template and keeps the product table, so
staging can be checked against it (and switched back). The second removes the product table and
the product-side calculation.

**Templates.** New check **Calculate Configurator on Save** (`auto_populate_configurator`,
default on) above the Part No. Configurator. On: the steps are rebuilt on every save (Is Required
choices kept). Off: the steps are set up by hand and the save leaves them alone (specifications are
still calculated).

**Readers.** A product linked to a template (the template's Webflow Product points back at it) now
reads the template's `part_no_configurator`; a product without a template still reads its own table.
The payload key stays `configurator_options`, so n8n and the Webflow scripts do not change.

| Reader | How |
|---|---|
| Webflow export (`webflow_export`, `webflow_export_v2`) | `Listing` reads `configurator_options` from the template |
| Readiness checks (`product_readiness.evaluate`) | same, through `Listing.as_dict` |
| Portal product detail (`product_catalog.get_catalog_product_detail`) | `template_listing.configurator_rows` |
| Product finder facts (`portal/product_finder/facts.py`) | same, one query per template type |
| Catalog Configurability report | same |

Site config `web_listing_legacy_read: 1` sends all of them back to the product's table, as before.

**Products.** The product's Configurator Options and its Auto-Populate check are read-only once the
product is linked to a template, with a note to edit the template.

**Until each hand-set product is decided** (a product with Auto-Populate off whose template still
calculates), readers keep showing the product's own steps (`template_listing.pending_decision`), so
the website does not change before the owner chooses. Added after the first dry run.

**Owner decisions on the first dry run (2026-11-02):** Tape/Neon and fixtures with hand-set
steps keep them (the narrower fixture choices are deliberate; the Tape/Neon step layout is the one
the website uses). The 10 fixtures with no steps take the calculated ones. The goal is still that
every template calculates; each one is switched back once its template options match what is sold,
without breaking the website.

**Hand-set configurators (owner decision, 2026-11-02).** 55 products have steps set up by hand
(Auto-Populate off), and the website shows those steps today. To keep the website as it is, their
templates take those steps and stop calculating (Calculate Configurator on Save off). The owner can
switch any template back to calculated steps later by ticking the check.

**Second dry run (2026-11-02):** 45 adopted (26 fixtures, 19 Tape/Neon), 10 with no steps take the
calculated ones, none failed. It also showed that the hand-set fixture steps still offer the old
Environment Rating codes (I, and I/D/O on SH03-SW/TW) instead of 20/54/67, so the website builds
part numbers with "I", and carry an older output-level lookup (10 entries, 15 calculated). Before a
template takes hand-set steps, `refresh_hand_set` brings that data up to date and keeps the
choices: old Environment Rating codes become the current ones (I 20, D 54, O 67), and on fixtures
the lookup steps 98 and 99 come from the calculation. Each change is listed under `refreshed`.
Not changed: Is Required (steps 7 to 11 stay optional on the website, as today).

`template_listing.adopt_hand_set_configurators`, System Manager only, dry run by default:

- `adopted`: templates that take the product's steps, with `same_steps` and each step that differs
  (`hand_set` next to `calculated`: type / label and how many values).
- `identical`: products whose hand-set steps equal the calculated ones. Nothing changes: their
  templates keep calculating.
  For a step whose summary looks the same, `differs` names the fields that differ
  (`is_required`, `depends_on_step`, `option_description`, allowed values) and
  `only_hand_set` / `only_calculated` list the allowed values on one side only.
- `empty_on_product`: products with no steps at all (no configurator on the website today). They
  switch to the calculated steps (owner, 2026-11-02), so they are also listed in `kept_calculated`.
- `kept_calculated`: products named in `use_calculated`. With `apply` their Auto-Populate is turned
  back on and they show the template's calculated steps.
- `already_hand_set`, `failed`.

## 2c: checks on staging

1. Deploy and migrate (the six templates and the Webflow Product changed).
2. Dry run, and send the output:

   ```python
   import json
   from illumenate_lighting.illumenate_lighting.template_listing import adopt_hand_set_configurators
   print(json.dumps(adopt_hand_set_configurators(), default=str, indent=1))
   ```

3. Apply, leaving out any product whose template should use the calculated steps:

   ```python
   print(json.dumps(adopt_hand_set_configurators(apply=True, use_calculated=[]), default=str, indent=1))
   ```

4. Compare every export payload with the old path (`[]` means no payload changed):

   ```python
   print(frappe.call("illumenate_lighting.illumenate_lighting.web_listing_source.payload_parity"))
   ```

   Products listed with `configurator_options` are the stale ones from 2a (stored steps older than
   the template's); anything else listed is a bug.

## 2c: result on staging and what stays (2026-11-02)

Applied: 45 templates took their products' hand-set steps (26 fixtures with current Environment
Rating codes and lookups, 19 Tape/Neon unchanged); the 10 fixtures with no steps (RA01 to RA05 DW,
the four RA06, SH03-DW) show the calculated ones. They have no Target Brand, so they are not exported
to Webflow until they get one. `payload_parity` lists `configurator_options` only on the 26 fixtures
and on 16 products whose stored steps were older than their own calculation (controllers `bled`,
`dmxc-rgbtw`, `dmxc-tw`, `dmxd`, not configurable, lose unused leftover rows; kits `kit-az01`,
`kit-ch02`, `kit-ra04`, `kit-ra05`, `kit-sh01`, `kit-sh02`, `kit-sh03`, `kit-sl01`; tape
`led-snf-sw`, `led-snf-tw`; neon `non-uch-sw`, `non-ucl-sw`).

**Owner, 2026-11-02: the product's Configurator Options table, its Auto-Populate check and the
product-side calculation stay for now**, so nothing breaks. They are removed later, after the
remaining templates calculate their own steps.

**Catalog import points at the template.** The fixture builder no longer writes placeholder
configurator steps onto new Webflow Products (the template calculates them on import), and no
longer asks for a step order (`configurator_steps` in older YAML files is read and ignored). In the
Catalog Builder the product's Configurator Options and Auto-Populate are read-only, shown only when
a record already has them; steps are authored on the template (Part No. Configurator, Calculate
Configurator on Save).
