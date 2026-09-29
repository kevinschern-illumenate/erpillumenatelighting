# Version 2 product catalog contract

The catalog editor and CLI cover product-master inputs to the ERP's current
configurators. The app creates configured Items, BOMs, cut plans, project lines,
and sales transactions when a customer configuration is resolved; these are not
product onboarding records.

## Product coverage

| Family | Engineering and template records | Related authoring records |
| --- | --- | --- |
| Linear fixture | Profile, lens, accessory, LED tape specs; Fixture Template | Tape offerings/options, part-number builder, profile/lens compatibility, mounting/endcap maps, finish/endcap colors, leader cables, driver eligibility |
| LED tape / neon | LED Tape spec; Tape Neon Template | Tape offerings, allowed specs/options, feed positions, production interval, bending limits, free cutting, leader cables, mounting accessories, drivers |
| LED sheet | LED Sheet spec; LED Sheet Template | Dimensions/cut intervals, full-panel watts, input protocol, allowed specs/options, leader/jumper Items, driver eligibility |
| Extrusion kit | Profile, lens, accessory specs; Extrusion Kit Template | Allowed options, component quantities, kit profile/lens/endcap/mounting maps |
| Driver | Driver spec; Driver Template | Physical/independent outputs, load factor, per-output watts, protocols, variants, option codes, pricing, certifications |
| Controller | Controller spec; Controller Template | Channels/zones, electrical limits, input/output/wireless protocols, compatible drivers, variants, options |

The editor exposes all shipped product `ilL-Attribute-*`, `ilL-Spec-*`, `ilL-Rel-*`,
product templates and submittal mappings, plus Webflow Product/Category and every
child table reachable from those records. This currently comprises 65 parent
DocTypes and 37 child DocTypes, including the standard master-data subset below.

Standard ERPNext master support includes Item (variant attributes and supplier
parts), Item Attribute/values, Item Group, UOM, Brand, and Item Price. Each Supplier
Items row takes a Supplier, Supplier Part Number, and Supplier Description; the
description is the site's `custom_supplier_description` field, exported under its
`supplier_items.custom_supplier_description` header. Existing
Supplier, Price List, Currency and site integration records can be referenced
through explicit external links. Standard metadata is an explicit ERPNext v15
subset; custom product metadata is derived from the checked-in JSON.

Extrusion kits have a dedicated ERP kit configurator. The current Webflow Product
DocType has kit component rows but **no kit-template Link field**; the builder does
not invent one. Its kit example generates the dedicated template and all four maps.

## YAML structure

```yaml
schema_version: 2
product_type: driver
series_name: My driver family
records:
  Item:
    - item_code: PS-EXAMPLE
      item_group: Drivers
      stock_uom: Nos
  # Add ilL-Spec-Driver and ilL-Driver-Template records, including child rows.
external_links:
  Item Group: [Drivers]
  UOM: [Nos]
```

Use `catalog_<product-type>.yaml` for complete illustrative examples. Record keys
are **DocType fieldnames**, and child tables are lists of mappings. Use `name` for
prompt-named records such as LED Package. Quote numeric-looking names (`"90"`,
`"3"`, `"001"`); use numbers for Float/Int/Currency fields and booleans or 0/1 for Check.
Lists and objects in JSON fields serialize as JSON in the corresponding CSV cell.

Unknown fields/types, malformed child rows, invalid enum values, duplicate names,
missing required values, nonfinite numbers, unresolved links, ambiguous active
driver/controller variants, and empty active template specification lists fail
validation. The existing `api/authoring_contract.py` supplies engineering checks.
Every linked record must be generated or explicitly declared external, including
Dynamic Links and links in child rows. Declaring a dependency does not verify it.

## CSV and import behavior

The generator uses current DocType labels for CSV headers and Frappe's
`Child Label (Parent Table Label)` convention, with fieldname fallback for duplicate
labels. Parent values appear only on the first row; independent child tables share
aligned continuation rows. This follows the [Frappe v15 Data Import exporter](https://github.com/frappe/frappe/blob/version-15/frappe/core/doctype/data_import/exporter.py).

Generation validates the complete catalog before creating files. It sorts records
by static and dynamic Link dependencies, then groups ready records into numbered
CSV batches. Import **only the files in manifest order**, using each listed DocType
and `Insert New Records`. Existing records belong in `external_links`; updating
already imported records requires an ERPNext update workflow, not replaying an
insert package. `records.json` is an audit artifact, not an automatic importer.

Circular references are reported before export. For a template/product cycle,
omit the template's optional `webflow_product` reverse link, import the product's
forward template link, then set the reverse link in ERPNext if needed. Other
cycles also require removing optional back-references or referencing existing records.

Site validation must still check custom fields, existing names, UOM conversions,
actual engineering ratings, compatible combinations, physical files, PDF field
names, imagery and descriptions, and current publication permissions. Importing a
catalog does not approve, publish, synchronize, or price a customer order.

## Design and verification

Version 2 uses DocType metadata directly because duplicating every new field in
hand-written dataclasses/forms was losing fields between authoring and generation.
Legacy family expansion remains available for compact convention-based configs.
Browser metadata is checked against repository metadata at build time; catalog
generation always reads current repository metadata.

```powershell
python -m tools.fixture_builder.catalog_schema --check
python -m unittest discover -s tools/fixture_builder/tests -q
cd tools/yaml_builder_ui
npm test
npm run test:render
npm run build
```

Tests cover all seven example round trips, dependency ordering, duplicate records,
dynamic links, missing Items, engineering failures, same-DocType dependency batches,
child tables sharing a DocType, and legacy export regressions. React server rendering
checks the shell, example fields, and the family expansion editor. These checks do
not substitute for a staging-site Data Import rehearsal.
